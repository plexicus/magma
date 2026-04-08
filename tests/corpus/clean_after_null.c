#include <stdlib.h>

void clean_after_null() {
    int *ptr = (int *)malloc(sizeof(int));
    free(ptr);
    ptr = NULL;    // Nullification — anti-pattern exclusion
    // Using NULL would crash, but this is a NULL deref, not a UAF
}
