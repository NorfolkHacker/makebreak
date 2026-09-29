/* gate.c — MAKE / BREAK issue #04: "Make it confess"
 *
 * It wants a password. It will not tell you what it is.
 * Your job: get in WITHOUT running it to guess — read what it does.
 *   gcc -O0 -o gate gate.c
 *   strings gate            # the free win
 *   objdump -d -M intel gate | grep -A40 '<main>:'
 * Full walkthrough: https://makebreak.co.uk/issues/04.html
 */
#include <stdio.h>
#include <string.h>

int main(void) {
    char buf[64];
    printf("password: ");
    if (!fgets(buf, sizeof buf, stdin)) return 1;
    buf[strcspn(buf, "\n")] = 0;              /* chop the newline */

    /* the "secret", lightly scrambled so it isn't sitting in plain sight */
    unsigned char key[] = { 0x47,0x4b,0x41,0x4f,0x48,0x58,0x4f,0x4b,0x41, 0 };

    int ok = (strlen(buf) == 9);
    for (int i = 0; i < 9; i++)
        if (((unsigned char)buf[i] ^ 0x2a) != key[i]) ok = 0;

    puts(ok ? "ACCESS GRANTED" : "nope.");
    return !ok;
}
