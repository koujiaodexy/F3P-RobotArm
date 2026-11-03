/* GTK3 draw signal adapter. No GI Cairo converter, system changes or motor APIs.
 * Build: gcc -O2 -fPIC -shared canvas.c -o canvas.so -Wl,--no-undefined
 *   -l:libgtk-3.so.0 -l:libgdk-3.so.0 -l:libgobject-2.0.so.0
 *   -l:libcairo.so.2 -l:libpangocairo-1.0.so.0 -l:libpango-1.0.so.0 -lm
 * GTK/Cairo opaque public ABI declarations keep target development headers optional.
 */
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <stdint.h>
#include <math.h>
#include <time.h>
typedef void Surface;typedef void Context;
extern Surface *cairo_image_surface_create(int,int,int);
extern void cairo_surface_destroy(Surface*),cairo_surface_flush(Surface*);
extern unsigned char *cairo_image_surface_get_data(Surface*);
extern int cairo_image_surface_get_stride(Surface*);
extern int cairo_surface_status(Surface*);
extern void cairo_clip_extents(Context*,double*,double*,double*,double*);
extern Context *cairo_create(Surface*);
extern void cairo_destroy(Context*),cairo_save(Context*),cairo_restore(Context*);
extern void cairo_set_source_surface(Context*,Surface*,double,double);
extern void cairo_set_source_rgba(Context*,double,double,double,double);
extern void cairo_set_operator(Context*,int),cairo_paint(Context*);
extern void cairo_move_to(Context*,double,double),cairo_line_to(Context*,double,double);
extern void cairo_set_line_width(Context*,double),cairo_set_line_cap(Context*,int);
extern void cairo_stroke(Context*),cairo_fill(Context*),cairo_arc(Context*,double,double,double,double,double);
extern void cairo_rectangle(Context*,double,double,double,double),cairo_clip(Context*);
extern void gdk_cairo_set_source_pixbuf(Context*,void*,double,double);
extern void gtk_widget_queue_draw_area(void*,int,int,int,int);
extern unsigned long g_signal_connect_data(void*,const char*,void*,void*,void*,int);
extern void g_object_unref(void*);
extern void *pango_cairo_create_layout(Context*),*pango_font_description_new(void);
extern void pango_font_description_set_family(void*,const char*),pango_font_description_set_absolute_size(void*,double);
extern void pango_layout_set_font_description(void*,void*),pango_layout_set_text(void*,const char*,int);
extern int pango_layout_get_baseline(void*);
extern void pango_layout_get_pixel_size(void*,int*,int*),pango_cairo_show_layout(Context*,void*),pango_font_description_free(void*);
typedef struct {double x,y,r;int number;} Marker;
typedef struct {int key,w,h,baseline;unsigned age;Surface *surface;} Glyph;
typedef struct {
 void *widget;Surface *background,*route,*ending,*snapshot;int w,h,active,prepared;
 Marker markers[20];int count;double tx,ty,lastx,lasty;int haslast;
 Glyph glyphs[64];unsigned clock,revision,painted;unsigned char *rgba;double draw_ms,draw_area;
} Canvas;
static void layer(Context *cr,Surface *s){if(s){cairo_set_source_surface(cr,s,0,0);cairo_paint(cr);}}
static void clear_surface(Surface *s){Context *cr=cairo_create(s);cairo_set_operator(cr,0);cairo_paint(cr);cairo_destroy(cr);}
static void copy_pixbuf(Surface *s,void *pix,int x,int y){clear_surface(s);if(pix){Context *cr=cairo_create(s);gdk_cairo_set_source_pixbuf(cr,pix,x,y);cairo_paint(cr);cairo_destroy(cr);}}
static Glyph *glyph(Canvas *s,int key){
 Glyph *g=&s->glyphs[0];for(int i=0;i<64;i++){if(s->glyphs[i].surface&&s->glyphs[i].key==key){g=&s->glyphs[i];goto found;}if(!s->glyphs[i].surface||s->glyphs[i].age<g->age)g=&s->glyphs[i];}
 if(g->surface)cairo_surface_destroy(g->surface);
 char text[32];if(key<0)strcpy(text,"目标");else snprintf(text,sizeof(text),"%d",key);
 Surface *probe=cairo_image_surface_create(0,1,1);Context *cr=cairo_create(probe);void *p=pango_cairo_create_layout(cr),*font=pango_font_description_new();
 pango_font_description_set_family(font,"serif");pango_font_description_set_absolute_size(font,11*1024.0);pango_layout_set_font_description(p,font);pango_layout_set_text(p,text,-1);
 pango_layout_get_pixel_size(p,&g->w,&g->h);g->baseline=pango_layout_get_baseline(p);g->surface=cairo_image_surface_create(0,g->w+2,g->h+2);Context *out=cairo_create(g->surface);
 if(key<0)cairo_set_source_rgba(out,74/255.,122/255.,194/255.,1);else cairo_set_source_rgba(out,83/255.,108/255.,144/255.,1);
 pango_cairo_show_layout(out,p);cairo_destroy(out);pango_font_description_free(font);g_object_unref(p);cairo_destroy(cr);cairo_surface_destroy(probe);g->key=key;
 found:g->age=++s->clock;return g;
}
static void text(Canvas *s,Context *cr,int key,double x,double baseline){
 char digits[16];if(key<0)strcpy(digits,"x");else snprintf(digits,sizeof(digits),"%d",key);
 for(const char *p=digits;*p;p++){Glyph *g=glyph(s,key<0?-1:*p-'0');cairo_set_source_surface(cr,g->surface,x,baseline-g->baseline/1024.);cairo_paint(cr);x+=g->w;}
}
static void paint(Canvas *s,Context *cr){
 layer(cr,s->background);layer(cr,s->route);
 for(int i=0;i<s->count;i++){Marker m=s->markers[i];cairo_set_source_rgba(cr,192/255.,134/255.,64/255.,1);cairo_arc(cr,m.x,m.y,m.r,0,6.283185307179586);cairo_fill(cr);text(s,cr,m.number,m.x+6,m.y-4);}
 cairo_set_source_rgba(cr,74/255.,122/255.,194/255.,1);cairo_arc(cr,s->tx,s->ty,6,0,6.283185307179586);cairo_fill(cr);text(s,cr,-1,s->tx+8,s->ty-5);layer(cr,s->ending);
}
static int draw(void *widget,Context *cr,Canvas *s){(void)widget;if(!s->active)return 0;struct timespec a,b;double x1,y1,x2,y2;clock_gettime(CLOCK_MONOTONIC,&a);cairo_clip_extents(cr,&x1,&y1,&x2,&y2);layer(cr,s->snapshot);clock_gettime(CLOCK_MONOTONIC,&b);s->draw_ms=(b.tv_sec-a.tv_sec)*1000.+(b.tv_nsec-a.tv_nsec)/1e6;s->draw_area=(x2-x1)*(y2-y1);s->painted=s->revision;return 1;}
static void dispose(Canvas *s,void *closure){(void)closure;Surface *v[]={s->background,s->route,s->ending,s->snapshot};for(int i=0;i<4;i++)if(v[i])cairo_surface_destroy(v[i]);for(int i=0;i<64;i++)if(s->glyphs[i].surface)cairo_surface_destroy(s->glyphs[i].surface);free(s->rgba);free(s);}
int f3p_canvas_abi(void){return 1;}
Canvas *f3p_canvas_new(void *widget){if(!widget)return NULL;Canvas *s=calloc(1,sizeof(*s));if(!s)return NULL;s->widget=widget;g_signal_connect_data(widget,"draw",(void*)draw,s,(void*)dispose,0);return s;}
int f3p_canvas_prepare(Canvas *s,int w,int h,void *bg,void *route,int rx,int ry,void *ending,int ex,int ey,double lx,double ly,int haslast){
 if(!s||w<1||h<1||w>8192||h>8192||(size_t)w*h>16777216||!bg||!isfinite(lx)||!isfinite(ly))return 0;
 s->active=0;s->prepared=0;
 if(w!=s->w||h!=s->h){Surface **v[]={&s->background,&s->route,&s->ending,&s->snapshot};for(int i=0;i<4;i++){if(*v[i])cairo_surface_destroy(*v[i]);*v[i]=cairo_image_surface_create(i==0||i==3?1:0,w,h);}free(s->rgba);s->rgba=malloc((size_t)w*h*4);s->w=w;s->h=h;if(!s->rgba)return 0;}
 if(cairo_surface_status(s->background)||cairo_surface_status(s->route)||cairo_surface_status(s->ending)||cairo_surface_status(s->snapshot))return 0;
 copy_pixbuf(s->background,bg,0,0);copy_pixbuf(s->route,route,rx,ry);copy_pixbuf(s->ending,ending,ex,ey);
 s->lastx=lx;s->lasty=ly;s->haslast=haslast;s->count=0;s->prepared=1;s->revision++;return 1;
}
void f3p_canvas_seed(Canvas *s,const double *markers,int count,double tx,double ty){if(!s||!s->prepared||count<0||count>20)return;s->count=count;s->tx=tx;s->ty=ty;for(int i=0;i<count;i++)s->markers[i]=(Marker){markers[4*i],markers[4*i+1],markers[4*i+2],(int)markers[4*i+3]};for(int i=-1;i<10;i++)glyph(s,i);Context *cr=cairo_create(s->snapshot);paint(s,cr);cairo_destroy(cr);s->active=1;gtk_widget_queue_draw_area(s->widget,0,0,s->w,s->h);}
static void include(double *b,double x,double y,double r){if(x-r<b[0])b[0]=x-r;if(y-r<b[1])b[1]=y-r;if(x+r>b[2])b[2]=x+r;if(y+r>b[3])b[3]=y+r;}
int f3p_canvas_append(Canvas *s,const double *xy,int n,const double *markers,int count,double tx,double ty){
 if(!s||!s->prepared||!xy||n<1||n>10000||count<0||count>20||!isfinite(tx)||!isfinite(ty)||fabs(tx)>1e7||fabs(ty)>1e7)return 0;
 for(int i=0;i<2*n;i++)if(!isfinite(xy[i])||fabs(xy[i])>1e7)return 0;
 for(int i=0;i<count;i++){for(int j=0;j<4;j++)if(!isfinite(markers[4*i+j])||fabs(markers[4*i+j])>1e7)return 0;if(markers[4*i+2]<0||markers[4*i+2]>100||markers[4*i+3]<1||markers[4*i+3]>10000)return 0;}
 double b[]={s->w,s->h,0,0};if(s->tx!=tx||s->ty!=ty){include(b,s->tx+22,s->ty-5,32);include(b,tx+22,ty-5,32);}
 Context *cr=cairo_create(s->route);cairo_set_source_rgba(cr,192/255.,134/255.,64/255.,1);cairo_set_line_width(cr,2);cairo_set_line_cap(cr,1);
 if(s->haslast){cairo_move_to(cr,s->lastx,s->lasty);include(b,s->lastx,s->lasty,3);}
 for(int i=0;i<n;i++){double x=xy[2*i],y=xy[2*i+1];if(!isfinite(x)||!isfinite(y)){cairo_destroy(cr);return 0;}if(s->haslast||i)cairo_line_to(cr,x,y);else cairo_move_to(cr,x,y);include(b,x,y,3);}
 cairo_stroke(cr);cairo_destroy(cr);s->lastx=xy[2*n-2];s->lasty=xy[2*n-1];s->haslast=1;
 Marker next[20];for(int i=0;i<count;i++){next[i]=(Marker){markers[4*i],markers[4*i+1],markers[4*i+2],(int)markers[4*i+3]};}
 for(int side=0;side<2;side++){Marker *a=side?next:s->markers,*other=side?s->markers:next;int length=side?count:s->count,otherlen=side?s->count:count;
  for(int i=0;i<length;i++){int unchanged=0;for(int j=0;j<otherlen;j++)if(a[i].number==other[j].number&&a[i].x==other[j].x&&a[i].y==other[j].y&&a[i].r==other[j].r)unchanged=1;if(!s->active||!unchanged){include(b,a[i].x,a[i].y,8);include(b,a[i].x+35,a[i].y-10,32);}}
 }
 memcpy(s->markers,next,count*sizeof(Marker));s->count=count;s->tx=tx;s->ty=ty;s->active=1;s->revision++;
 int x=(int)fmax(0,floor(b[0]-1)),y=(int)fmax(0,floor(b[1]-1)),right=(int)fmin(s->w,ceil(b[2]+1)),bottom=(int)fmin(s->h,ceil(b[3]+1));
 if(right>x&&bottom>y){Context *frame=cairo_create(s->snapshot);cairo_rectangle(frame,x,y,right-x,bottom-y);cairo_clip(frame);paint(s,frame);cairo_destroy(frame);gtk_widget_queue_draw_area(s->widget,x,y,right-x,bottom-y);}else{s->painted=s->revision;}return 1;
}
void f3p_canvas_deactivate(Canvas *s){if(s)s->active=0;}
unsigned f3p_canvas_painted(Canvas *s){return s?s->painted:0;}
double f3p_canvas_draw_ms(Canvas *s){return s?s->draw_ms:0;}
double f3p_canvas_draw_area(Canvas *s){return s?s->draw_area:0;}
unsigned char *f3p_canvas_snapshot(Canvas *s){
 if(!s||!s->prepared||!s->active||!s->rgba)return NULL;cairo_surface_flush(s->snapshot);
 unsigned char *src=cairo_image_surface_get_data(s->snapshot);int stride=cairo_image_surface_get_stride(s->snapshot);
 for(int y=0;y<s->h;y++)for(int x=0;x<s->w;x++){unsigned char *a=src+y*stride+4*x,*b=s->rgba+((size_t)y*s->w+x)*4;b[0]=a[2];b[1]=a[1];b[2]=a[0];b[3]=255;}return s->rgba;
}
