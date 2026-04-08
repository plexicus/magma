#include <stdlib.h>

void uaf_branch(int cond) {
    int *ptr = (int *)malloc(sizeof(int));
    if (cond) {
        free(ptr);
    }
    *ptr = 1;  // UAF: may dereference after conditional free
}
