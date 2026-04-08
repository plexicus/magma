#include <stdlib.h>

void uaf_loop(int n) {
    int *ptr = (int *)malloc(sizeof(int));
    free(ptr);
    for (int i = 0; i < n; i++) {
        *ptr = i;  // UAF: dereference in loop after free
    }
}
