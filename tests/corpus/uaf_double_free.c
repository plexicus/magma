#include <stdlib.h>

void uaf_double_free() {
    int *ptr = (int *)malloc(sizeof(int));
    free(ptr);
    free(ptr);  // UAF: double free
}
