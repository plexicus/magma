#include <stdlib.h>

void clean_realloc() {
    int *ptr = (int *)malloc(sizeof(int));
    ptr = (int *)realloc(ptr, 2 * sizeof(int));
    *ptr = 42;     // Use after realloc — correct
    free(ptr);
}
