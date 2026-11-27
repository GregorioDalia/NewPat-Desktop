"""Run the same native-window fixture in the system Cocoa/WKWebView host."""
from newpat.desktop.macos_host import run_window
from test_gui_windows_native import main

if __name__ == "__main__":
    main(run_native_window=run_window, expected_host="cocoa-wkwebview")
