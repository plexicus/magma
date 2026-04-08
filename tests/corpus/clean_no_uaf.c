#include <stdlib.h>

void clean_no_uaf() {
    int *ptr = (int *)malloc(sizeof(int));
    *ptr = 42;     // Use before free — correct
    int x = *ptr;  // Use before free — correct
    free(ptr);     // Free last — correct
}
