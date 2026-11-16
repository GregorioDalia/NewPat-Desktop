/* Open the native desktop GUI using bundled Python; no Terminal or browser. */
#include <mach-o/dyld.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(void) {
    char executable[PATH_MAX], real[PATH_MAX], command[PATH_MAX], python[PATH_MAX];
    uint32_t size = sizeof executable;
    if (_NSGetExecutablePath(executable, &size) != 0 || !realpath(executable, real))
        return 1;
    char *directory = strrchr(real, '/');
    if (!directory) return 1;
    *directory = '\0';
    directory = strrchr(real, '/');
    if (!directory) return 1;
    *directory = '\0';
    if (snprintf(command, sizeof command, "%s/Resources/app/installer/macos/launch.py", real)
        >= (int)sizeof command) return 1;
    if (snprintf(python, sizeof python, "%s/Resources/python/bin/python3.12", real)
        >= (int)sizeof python) return 1;
    execl(python, python, "-I", "-B", command, "gui", (char *)NULL);
    perror("NewPat: desktop");
    return 1;
}
