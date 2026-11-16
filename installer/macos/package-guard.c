/* Package transactions coordinate with CLI sessions without stopping analyses. */
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

#define STATE "/Library/Application Support/NIPAT-Desktop Installer"
#define LOCK STATE "/activity.lock"
#define MARKER STATE "/update-in-progress"

static int fail(const char *message) {
    fprintf(stderr, "NewPat: %s\n", message);
    return 1;
}

int main(int argc, char **argv) {
    (void)argc;
    struct stat info;
    if (geteuid() != 0) return fail("Installer must run as administrator.");
    umask(022);
    if (mkdir(STATE, 0755) < 0 && errno != EEXIST) return fail("Cannot create package state.");
    if (lstat(STATE, &info) < 0 || !S_ISDIR(info.st_mode) || info.st_uid != 0
        || (info.st_mode & 0777) != 0755) return fail("Unsafe package state directory.");
    int descriptor = open(LOCK, O_CREAT | O_RDONLY | O_NOFOLLOW, 0644);
    if (descriptor < 0 || fstat(descriptor, &info) < 0 || !S_ISREG(info.st_mode)
        || info.st_uid != 0 || (info.st_mode & 0777) != 0644)
        return fail("Unsafe package activity lock.");
    if (flock(descriptor, LOCK_EX | LOCK_NB) < 0)
        return fail("Close all NewPat and NIPAT sessions before installing.");
    const char *name = strrchr(argv[0], '/');
    name = name ? name + 1 : argv[0];
    if (strcmp(name, "preinstall") == 0) {
        const char *app = "/Applications/NewPat.app";
        if (lstat(app, &info) == 0 && (!S_ISDIR(info.st_mode) || info.st_uid != 0 || (info.st_mode & 0022)))
            return fail("Application destination is not an installer-owned directory.");
        int marker = open(MARKER, O_CREAT | O_WRONLY | O_NOFOLLOW, 0644);
        if (marker < 0 || fstat(marker, &info) < 0 || !S_ISREG(info.st_mode)
            || info.st_uid != 0) return fail("Unsafe package update marker.");
        close(marker);
    } else if (strcmp(name, "postinstall") == 0) {
        /* The new verified payload exists before the legacy bundle is archived.
           Never remove a user directory or delete any analysis/runtime data. */
        const char *python = "/Applications/NewPat.app/Contents/Resources/python/bin/python3.12";
        const char *migration = "/Applications/NewPat.app/Contents/Resources/app/installer/macos/migrate_legacy.py";
        const char *directories[] = {
            "/Applications/NewPat.app", "/Applications/NewPat.app/Contents",
            "/Applications/NewPat.app/Contents/Resources",
            "/Applications/NewPat.app/Contents/Resources/python",
            "/Applications/NewPat.app/Contents/Resources/python/bin",
            "/Applications/NewPat.app/Contents/Resources/app",
            "/Applications/NewPat.app/Contents/Resources/app/installer",
            "/Applications/NewPat.app/Contents/Resources/app/installer/macos"
        };
        for (unsigned int index = 0; index < sizeof(directories) / sizeof(directories[0]); index++) {
            if (lstat(directories[index], &info) < 0 || !S_ISDIR(info.st_mode)
                || info.st_uid != 0 || (info.st_mode & 0022))
                return fail("New application contains an unsafe directory.");
        }
        if (lstat(python, &info) < 0 || !S_ISREG(info.st_mode) || info.st_uid != 0
            || (info.st_mode & 0022) || !(info.st_mode & 0111))
            return fail("New application Python is not installer-owned or executable.");
        if (lstat(migration, &info) < 0 || !S_ISREG(info.st_mode) || info.st_uid != 0 || (info.st_mode & 0022))
            return fail("New application migration helper is not installer-owned.");
        pid_t child = fork();
        if (child < 0) return fail("Cannot start legacy application migration.");
        if (child == 0) {
            execl(python, python, "-I", "-B", migration, (char *)NULL);
            _exit(127);
        }
        int result;
        if (waitpid(child, &result, 0) < 0 || !WIFEXITED(result) || WEXITSTATUS(result) != 0)
            return fail("Cannot complete legacy application migration.");
        if (unlink(MARKER) < 0 && errno != ENOENT) return fail("Cannot complete package transaction.");
    } else return fail("Unsupported package transaction.");
    close(descriptor);
    return 0;
}
