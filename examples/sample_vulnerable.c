#include <stdlib.h>
#include <stdio.h>

/* Example vulnerable C file for Magma testing.
 * Contains a simple Use-After-Free bug.
 */

void vulnerable_function(int size) {
    int *buffer = (int *)malloc(size * sizeof(int));
    if (buffer == NULL) {
        return;
    }

    // Use the buffer
    for (int i = 0; i < size; i++) {
        buffer[i] = i * 2;
    }

    free(buffer);

    // BUG: Use-After-Free — buffer is used after being freed
    buffer[0] = 42;

    printf("Value: %d\n", buffer[0]);
}
