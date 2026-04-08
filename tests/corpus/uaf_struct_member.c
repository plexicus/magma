#include <stdlib.h>

struct S {
    int field;
};

void uaf_struct_member() {
    struct S *obj = (struct S *)malloc(sizeof(struct S));
    free(obj);
    obj->field = 1;  // UAF: struct member dereference after free
}
