"""Exercise the native window's private HTTP boundary over actual loopback sockets."""
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import quote, urlsplit

from newpat.errors import RuntimeExecutionError
from newpat.desktop.igv import LocalIGV
from newpat.desktop.plan import prepare_analysis
from newpat.desktop.server import DesktopServer, MAX_RPC_BYTES, byte_range


class ByteRangeTests(unittest.TestCase):
    def test_full_open_suffix_and_clamped_ranges(self):
        self.assertIsNone(byte_range(None, 0))
        for value, expected in (("bytes=0-0", (0, 0)), ("bytes=2-", (2, 9)),
                                ("bytes=-3", (7, 9)), ("bytes=-99", (0, 9)),
                                ("bytes=1-99", (1, 9))):
            with self.subTest(value=value):
                self.assertEqual(byte_range(value, 10), expected)

    def test_invalid_unsatisfiable_and_multiple_ranges_fail(self):
        for value in ("bytes=", "bytes=-", "bytes=-0", "bytes=10-", "bytes=5-2",
                      "bytes=0-1,4-5", "items=0-1", "bytes=a-1", "bytes=+1-3"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                byte_range(value, 10)
        with self.assertRaises(ValueError):
            byte_range("bytes=0-", 0)


class DesktopTransportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.assets = self.root / "web"
        self.assets.mkdir()
        (self.assets / "index.html").write_text("<!doctype html><title>NIPAT</title>", encoding="utf-8")
        (self.assets / "app.js").write_text("window.app = 'NIPAT';", encoding="utf-8")
        self.secret = self.root / "private.txt"
        self.secret.write_bytes(b"private genomic bytes")
        self.calls = []

        def dispatch(method, params):
            self.calls.append((method, params))
            if method == "fail":
                raise ValueError("Selection unavailable")
            return {"method": method, "params": params}

        try:
            self.server = DesktopServer(dispatch, assets=self.assets).start()
        except PermissionError as exc:
            self.skipTest("Actual loopback sockets unavailable: " + str(exc))
        self.addCleanup(self.server.close)

    def request(self, method, route, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.httpd.server_port, timeout=4)
        try:
            connection.request(method, route, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def path(self, route):
        return "/" + self.server.token + "/" + route

    def rpc(self, payload, **headers):
        return self.request("POST", self.path("api"), json.dumps(payload),
                            {"Origin": self.server.origin, "Content-Type": "application/json", **headers})

    def test_loopback_only_random_session_token_and_security_headers(self):
        self.assertEqual(self.server.httpd.server_address[0], "127.0.0.1")
        self.assertGreaterEqual(len(self.server.token), 40)
        with DesktopServer(lambda *_: None, assets=self.assets) as second:
            self.assertNotEqual(self.server.token, second.token)
        status, headers, body = self.request("GET", self.path("web/index.html"))
        self.assertEqual(status, 200)
        self.assertIn(b"NIPAT", body)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertIn("connect-src 'self'", headers["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_missing_session_token_foreign_host_and_query_are_rejected(self):
        for route, headers in (("/web/index.html", {}), ("/wrong/health", {}),
                               (self.path("health"), {"Host": "attacker.example"}),
                               (self.path("health?extra=value"), {}),
                               (self.path("health#fragment"), {})):
            with self.subTest(route=route, headers=headers):
                self.assertEqual(self.request("GET", route, headers=headers)[0], 404)

    def test_asset_traversal_and_external_symlink_cannot_expose_files(self):
        for route in ("web/../private.txt", "web/%2e%2e/private.txt",
                      "web/%2e/private.txt", "web/..%5cprivate.txt", "web/%00private.txt",
                      "web//" + str(self.secret).lstrip("/")):
            with self.subTest(route=route):
                status, _, body = self.request("GET", self.path(route))
                self.assertEqual(status, 404)
                self.assertNotIn(b"private genomic bytes", body)
        link = self.assets / "linked.txt"
        try:
            link.symlink_to(self.secret)
        except (OSError, NotImplementedError):
            return  # Windows may not allow non-administrator symlink creation.
        self.assertEqual(self.request("GET", self.path("web/linked.txt"))[0], 404)

    def test_rpc_accepts_same_origin_json_and_preserves_error_envelope(self):
        status, _, body = self.rpc({"id": "abc", "method": "catalog.get", "params": {"language": "it"}})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"id": "abc", "result": {
            "method": "catalog.get", "params": {"language": "it"}}})
        status, _, body = self.rpc({"id": 12, "method": "fail"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"id": 12, "error": {
            "code": "ValueError", "message": "Selection unavailable"}})

    def test_foreign_or_missing_origin_and_non_json_never_dispatch(self):
        payload = json.dumps({"id": 1, "method": "analysis.start", "params": {}})
        for headers, expected in (({"Content-Type": "application/json"}, 403),
                                  ({"Content-Type": "application/json", "Origin": "null"}, 403),
                                  ({"Content-Type": "application/json", "Origin": "https://evil.test"}, 403),
                                  ({"Content-Type": "text/plain", "Origin": self.server.origin}, 415)):
            with self.subTest(headers=headers):
                status, response_headers, _ = self.request("POST", self.path("api"), payload, headers)
                self.assertEqual(status, expected)
                self.assertEqual(response_headers["Connection"], "close")
        self.assertEqual(self.calls, [])

    def test_actionable_igv_and_dnp_errors_reach_the_window(self):
        viewer = LocalIGV(self.server.register)
        fasta = self.root / "ref.fa"
        fasta.write_bytes(b">chr1\r\nACGT\r\n")
        Path(str(fasta) + ".fai").write_text("chr1\t4\t7\t4\t6\n")
        bam = self.root / "sample.bam"
        bam.write_bytes(b"BAM\x01")

        def dispatch(method, params):
            if method == "igv.prepare":
                return viewer.prepare(params)
            # Missing sample input is rejected before layout/runtime access.
            return prepare_analysis(params, None)

        self.server.dispatcher = dispatch
        cases = [
            ("igv.prepare", {}, "Seleziona FASTA."),
            ("igv.prepare", {"reference": {"fasta": str(fasta)},
                             "tracks": [{"path": ""}]}, "Seleziona traccia."),
            ("igv.prepare", {"reference": {"fasta": str(fasta)},
                             "tracks": [{"path": str(bam)}]}, "Seleziona l’indice BAI/CSI"),
            ("analysis.preview", {"name": "DNP", "caller": "dnp",
                                  "samples": [{"id": "sample", "kind": "bam", "path": ""}]},
             "Associare un file a ogni campione."),
        ]
        for method, params, expected in cases:
            with self.subTest(method=method, expected=expected):
                status, _, body = self.rpc({"id": "validation", "method": method, "params": params})
                result = json.loads(body)
                self.assertEqual(status, 200)
                self.assertEqual(result["id"], "validation")
                self.assertEqual(result["error"]["code"], "ValidationError")
                self.assertIn(expected, result["error"]["message"])

    def test_runtime_guidance_is_preserved_and_unexpected_errors_stay_private(self):
        def dispatch(method, params):
            if method == "runtime":
                raise RuntimeExecutionError("Avvia l’ambiente scientifico e riprova.")
            raise TypeError("private implementation details")

        self.server.dispatcher = dispatch
        _, _, body = self.rpc({"method": "runtime"})
        self.assertEqual(json.loads(body)["error"]["message"],
                         "Avvia l’ambiente scientifico e riprova.")
        with self.assertLogs("newpat.desktop.server", level="ERROR"):
            _, _, body = self.rpc({"method": "unexpected"})
        self.assertEqual(json.loads(body)["error"]["code"], "internal_error")
        self.assertNotIn(b"private implementation details", body)

    def test_invalid_json_and_envelopes_never_dispatch(self):
        bodies = ["{", "[]", '{"method":1}', '{"method":"x","params":[]}',
                  '{"method":"x","id":{}}', b"\xff",
                  '{"method":"x","params":{"value":NaN}}',
                  '{"method":"x","params":{"value":Infinity}}',
                  '{"method":"x","params":{"value":-Infinity}}',
                  '{"method":"x","params":{"value":' + '['*1500 + '0' + ']'*1500 + '}}']
        for body in bodies:
            with self.subTest(body=str(body)[:80]):
                status, _, response = self.request("POST", self.path("api"), body,
                    {"Origin": self.server.origin, "Content-Type": "application/json"})
                self.assertEqual(status, 400)
                self.assertEqual(json.loads(response)["error"]["code"], "invalid_request")
        self.assertEqual(len(self.calls), 0)

    def test_oversized_rpc_is_rejected_before_dispatch(self):
        status, headers, _ = self.request("POST", self.path("api"), b"", {
            "Origin": self.server.origin, "Content-Type": "application/json",
            "Content-Length": str(MAX_RPC_BYTES + 1)})
        self.assertEqual(status, 413)
        self.assertEqual(headers["Connection"], "close")
        self.assertEqual(self.calls, [])

    def test_resource_capability_ranges_and_head_preserve_original_bytes(self):
        data = bytes(range(256)) * 4096
        source = self.root / "sample with spaces.bam"
        source.write_bytes(data)
        registered = self.server.register(source)
        route = urlsplit(registered["url"]).path
        self.assertNotIn(str(source), registered["url"])
        self.assertEqual(self.request("GET", self.path("resources/" + quote(str(source))))[0], 404)
        self.assertEqual(self.request("GET", route)[2], data)
        for header, first, last in (("bytes=0-7", 0, 7), ("bytes=-9", len(data)-9, len(data)-1),
                                    ("bytes=1000000-", 1000000, len(data)-1)):
            with self.subTest(header=header):
                status, headers, body = self.request("GET", route, headers={"Range": header})
                self.assertEqual(status, 206)
                self.assertEqual(body, data[first:last+1])
                self.assertEqual(headers["Content-Range"], f"bytes {first}-{last}/{len(data)}")
                self.assertEqual(headers["Content-Length"], str(last-first+1))
        status, headers, body = self.request("HEAD", route, headers={"Range": "bytes=5-9"})
        self.assertEqual(status, 206)
        self.assertEqual(headers["Content-Length"], "5")
        self.assertEqual(body, b"")
        self.assertEqual(source.read_bytes(), data)

    def test_reference_range_refuses_replaced_file_after_opening_viewer(self):
        from newpat.experiments.tracking import input_stat_snapshot
        source = self.root / "genome.fa"
        source.write_bytes(b">a\nACGT\n")
        route = urlsplit(self.server.register(source, expected_identity=input_stat_snapshot(source.stat()))["url"]).path
        self.assertEqual(self.request("GET", route, headers={"Range": "bytes=3-6"})[2], b"ACGT")
        replacement = self.root / "replacement.fa"
        replacement.write_bytes(b">a\nTTTT\n")
        replacement.replace(source)
        self.assertEqual(self.request("GET", route, headers={"Range": "bytes=3-6"})[0], 409)

    def test_unsatisfiable_range_empty_file_and_removed_resource(self):
        path = self.root / "empty.bam"
        path.write_bytes(b"")
        route = urlsplit(self.server.register(path)["url"]).path
        self.assertEqual(self.request("GET", route)[0:3:2], (200, b""))
        status, headers, body = self.request("GET", route, headers={"Range": "bytes=0-"})
        self.assertEqual(status, 416)
        self.assertEqual(headers["Content-Range"], "bytes */0")
        self.assertEqual(body, b"")
        path.unlink()
        self.assertEqual(self.request("GET", route)[0], 404)
        with self.assertRaises(ValueError):
            self.server.register(self.root)

    def test_parallel_range_reads_use_independent_streams(self):
        source = self.root / "sample.bam"
        source.write_bytes(bytes(range(256)) * 16)
        route = urlsplit(self.server.register(source)["url"]).path
        def read(index):
            return self.request("GET", route, headers={"Range": f"bytes={index*128}-{index*128+127}"})
        with ThreadPoolExecutor(max_workers=6) as executor:
            responses = list(executor.map(read, range(16)))
        for index, (status, _, body) in enumerate(responses):
            self.assertEqual(status, 206)
            self.assertEqual(body, source.read_bytes()[index*128:index*128+128])

    def test_attachment_filename_cannot_inject_headers(self):
        source = self.root / "result ü.txt"
        source.write_text("original", encoding="utf-8")
        route = urlsplit(self.server.register(source, attachment=True)["url"]).path
        status, headers, body = self.request("GET", route)
        self.assertEqual(status, 200)
        self.assertEqual(body, b"original")
        self.assertTrue(headers["Content-Disposition"].startswith("attachment; filename*=UTF-8''"))
        self.assertIn("%C3%BC", headers["Content-Disposition"])


if __name__ == "__main__":
    unittest.main()
