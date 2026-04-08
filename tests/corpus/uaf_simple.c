#include <stdlib.h>

void uaf_simple() {
    int *ptr = (int *)malloc(sizeof(int));
    free(ptr);
    *ptr = 1;  // UAF: dereference after free
}
