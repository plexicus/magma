#include <stdlib.h>

void use_pointer(int *p);

void uaf_function_call() {
    int *ptr = (int *)malloc(sizeof(int));
    free(ptr);
    use_pointer(ptr);  // UAF: passed as argument after free
}
