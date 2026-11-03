#include "mission_main.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc,char **argv){
 if(argc==2&&!strcmp(argv[1],"--run"))return Mission_Run(0);
 if(argc==3&&!strcmp(argv[1],"--smoke")){
  char *end;long n=strtol(argv[2],&end,10);
  if(!*end&&n>=1&&n<=60)return Mission_Run((unsigned)n);
 }
 if(argc==3&&!strcmp(argv[1],"--render"))return Mission_Render(argv[2]);
 puts("F3P drive174-current: --run | --smoke 1..60 | --render FILE | --help\n"
      "Prepared shelf: touch start or KEY2; KEY4/GUI stop; idle task reset. Default does not open hardware.");
 return argc==1||(argc==2&&!strcmp(argv[1],"--help"))?0:2;
}
