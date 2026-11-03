// Stateless double-precision Craig MDH and bounded DLS IK. No Python or IO.
#include <cmath>
#include <algorithm>
#include <limits>
#include <cstring>
#include <initializer_list>
#ifdef _WIN32
#define API extern "C" __declspec(dllexport)
#else
#define API extern "C" __attribute__((visibility("default")))
#endif
static constexpr double PI=3.14159265358979323846;
static double deg(double x){return x*PI/180.;}
static double mod360(double x){double r=std::fmod(x,360.);return r<0?r+360:r;}
static double norm(const double *x,int n){double s=0;for(int i=0;i<n;i++)s+=x[i]*x[i];return std::sqrt(s);}
// Geometry: alpha,a,d,offsets (six each), offset_sign, optional TCP 4x4.
static void chain(const double*g,const double*q,double*t,double*axes,double*origins,double*points){
 double r[9]={1,0,0,0,1,0,0,0,1},p[3]={0,0,0};
 if(points)std::fill(points,points+3,0.);
 for(int i=0;i<6;i++){
  double ca=std::cos(deg(mod360(g[i]))),sa=std::sin(deg(mod360(g[i])));
  double ct=std::cos(deg(mod360(q[i]+g[24]*g[18+i]))),st=std::sin(deg(mod360(q[i]+g[24]*g[18+i])));
  for(int k=0;k<3;k++){
   double r0=r[k*3],r1=r[k*3+1],r2=r[k*3+2];
   double transverse=ca*r1+sa*r2,axial=-sa*r1+ca*r2,origin=p[k]+g[6+i]*r0;
   if(axes)axes[i*3+k]=axial;if(origins)origins[i*3+k]=origin;
   p[k]=origin+g[12+i]*axial;
   r[k*3]=ct*r0+st*transverse;r[k*3+1]=-st*r0+ct*transverse;r[k*3+2]=axial;
   if(points)points[(i+1)*3+k]=p[k];
  }
 }
 for(int i=0;i<3;i++){for(int j=0;j<3;j++)t[i*4+j]=r[i*3+j];t[i*4+3]=p[i];}
 t[12]=t[13]=t[14]=0;t[15]=1;
 if(g[25]){
  double temp[16]={0};for(int i=0;i<4;i++)for(int j=0;j<4;j++)for(int k=0;k<4;k++)temp[i*4+j]+=t[i*4+k]*g[26+k*4+j];
  std::copy(temp,temp+16,t);
 }
}
static void residual(const double*t,const double*target,double*e){
 for(int i=0;i<3;i++)e[i]=target[i*4+3]-t[i*4+3];
 double r[9]={0};for(int i=0;i<3;i++)for(int j=0;j<3;j++)for(int k=0;k<3;k++)r[i*3+j]+=target[i*4+k]*t[j*4+k];
 double w,x,y,z,tr=r[0]+r[4]+r[8];
 if(tr>0){double s=2*std::sqrt(std::max(0.,tr+1));w=s/4;x=(r[7]-r[5])/s;y=(r[2]-r[6])/s;z=(r[3]-r[1])/s;}
 else{
  int i=0;if(r[4]>r[0])i=1;if(r[8]>r[i*3+i])i=2;int j=(i+1)%3,k=(i+2)%3;
  double s=2*std::sqrt(std::max(1e-30,1+r[i*3+i]-r[j*3+j]-r[k*3+k])),v[3]={0};
  v[i]=s/4;v[j]=(r[i*3+j]+r[j*3+i])/s;v[k]=(r[i*3+k]+r[k*3+i])/s;
  w=(r[k*3+j]-r[j*3+k])/s;x=v[0];y=v[1];z=v[2];
 }
 double len=std::sqrt(w*w+x*x+y*y+z*z);w/=len;x/=len;y/=len;z/=len;
 if(w<0){w=-w;x=-x;y=-y;z=-z;}
 double n=std::sqrt(x*x+y*y+z*z),s=n<1e-12?2:2*std::atan2(n,std::max(0.,w))/n;
 e[3]=s*x;e[4]=s*y;e[5]=s*z;
}
static bool linear(double rows[6][7],double*out){
 for(int i=0;i<6;i++){
  int pivot=i;for(int j=i+1;j<6;j++)if(std::abs(rows[j][i])>std::abs(rows[pivot][i]))pivot=j;
  if(std::abs(rows[pivot][i])<1e-16)return false;
  for(int k=0;k<7;k++)std::swap(rows[i][k],rows[pivot][k]);
  double divisor=rows[i][i];for(int k=i;k<7;k++)rows[i][k]/=divisor;
  for(int j=0;j<6;j++)if(j!=i){double factor=rows[j][i];for(int k=i;k<7;k++)rows[j][k]-=factor*rows[i][k];}
 }
 for(int i=0;i<6;i++)out[i]=rows[i][6];return true;
}
API int f3p_math_abi(){return 1;}
static double polynomial_value(const double*c,int count,double x){double value=0;for(int i=count-1;i>=0;i--)value=value*x+c[i];return value;}
static double polynomial_bound(const double*c,int count,double lo,double hi,int order){
 static const int binomial[6][6]={{1},{1,1},{1,2,1},{1,3,3,1},{1,4,6,4,1},{1,5,10,10,5,1}};
 double d[6],power[6]={},lp[6]={1},wp[6]={1};std::copy(c,c+count,d);int degree=count-1;
 for(int n=0;n<order;n++){for(int i=0;i<degree;i++)d[i]=(i+1)*d[i+1];degree--;}
 for(int i=1;i<=degree;i++){lp[i]=lp[i-1]*lo;wp[i]=wp[i-1]*(hi-lo);}
 for(int i=0;i<=degree;i++){for(int j=i;j<=degree;j++)power[i]+=d[j]*binomial[j][i]*lp[j-i];power[i]*=wp[i];}
 double bound=0;
 for(int k=0;k<=degree;k++){double control=0;for(int i=0;i<=k;i++)control+=power[i]*binomial[k][i]/binomial[degree][i];bound=std::max(bound,std::abs(control));}
 return bound*(1+8*std::numeric_limits<double>::epsilon());
}
API double f3p_derivative_bound(const double*c,int count,double lo,double hi,int order){
 if(count<1||count>6||order<0||order>=count||hi<lo)return std::numeric_limits<double>::quiet_NaN();
 return polynomial_bound(c,count,lo,hi,order);
}
API double f3p_inverse_u(const double*c,double value,double begin,double end,int iterations){
 if(value<=begin)return 0;if(value>=end)return 1;double lo=0,hi=1;
 for(int i=0;i<iterations;i++){double mid=(lo+hi)/2;if(polynomial_value(c,6,mid)<value)lo=mid;else hi=mid;}
 return (lo+hi)/2;
}
API void f3p_timing_rates(const double*c,double duration,double begin,double end,double end_rate,double ahead,int count,const double*values,double*out){
 for(int i=0;i<count;i++){
  if(values[i]>=end){out[i]=end_rate;continue;}
  double x=f3p_inverse_u(c,values[i],begin,end,24),hi=std::min(1.,x+ahead/duration);
  out[i]=std::max(polynomial_bound(c,6,x,hi,1)/duration,hi==1?end_rate:0.);
 }
}
API void f3p_fk(const double*g,const double*q,double*t,double*axes,double*origins,double*points){chain(g,q,t,axes,origins,points);}
API void f3p_residual(const double*t,const double*target,double*e){residual(t,target,e);}
API void f3p_pose_norms(const double*t,const double*target,double*e){
 for(int i=0;i<3;i++)e[i]=target[i*4+3]-t[i*4+3];
 double trace=0;for(int i=0;i<3;i++)for(int j=0;j<3;j++)trace+=t[i*4+j]*target[i*4+j];
 double cosine=std::max(-1.,std::min(1.,(trace-1)/2));e[3]=cosine>=1-1e-15?0:std::acos(cosine);e[4]=e[5]=0;
}
API void f3p_fk_batch(const double*g,const double*q,int count,double*out){for(int i=0;i<count;i++)chain(g,q+i*6,out+i*16,nullptr,nullptr,nullptr);}
// Fused planning checks avoid building Python matrices for every frame.
API void f3p_q_pose_norms(const double*g,const double*q,const double*origin,const double*xyz,double*out){
 double t[16];chain(g,q,t,nullptr,nullptr,nullptr);double pe=0,trace=0;
 for(int i=0;i<3;i++){double d=xyz[i]-t[i*4+3];pe+=d*d;for(int j=0;j<3;j++)trace+=t[i*4+j]*origin[i*4+j];}
 double cosine=std::max(-1.,std::min(1.,(trace-1)/2));out[0]=std::sqrt(pe);out[1]=(cosine>=1-1e-15?0:std::acos(cosine))*180/PI;
}
API int f3p_path_tangent(const double*g,const double*q,const double*velocity,double*out){
 double t[16],axes[18],origins[18],jac[6][6],rows[6][7]={};chain(g,q,t,axes,origins,nullptr);
 for(int j=0;j<6;j++){double p[3];for(int i=0;i<3;i++)p[i]=t[i*4+3]-origins[j*3+i];
  for(int i=0;i<3;i++){int a=(i+1)%3,b=(i+2)%3;jac[i][j]=(axes[j*3+a]*p[b]-axes[j*3+b]*p[a])/200.;jac[i+3][j]=axes[j*3+i];}}
 for(int i=0;i<6;i++){for(int j=0;j<6;j++){for(int k=0;k<6;k++)rows[i][j]+=jac[k][i]*jac[k][j];if(i==j)rows[i][j]+=1e-10;}
  for(int k=0;k<3;k++)rows[i][6]+=jac[k][i]*velocity[k]/200.;}
 double result[6];if(!linear(rows,result))return 0;for(int i=0;i<6;i++)out[i]=result[i]*180/PI;return 1;
}
API int f3p_position_tangent(const double*g,const double*q,const double*velocity,const double*limits,double*out){
 double t[16],axes[18],origins[18],jac[3][6];bool active[6]={};chain(g,q,t,axes,origins,nullptr);
 for(int j=0;j<6;j++){double p[3];for(int i=0;i<3;i++)p[i]=t[i*4+3]-origins[j*3+i];
  for(int i=0;i<3;i++){int a=(i+1)%3,b=(i+2)%3;jac[i][j]=(axes[j*3+a]*p[b]-axes[j*3+b]*p[a])/200.;}}
 double bias[6]={},fixed[6]={},path_length=norm(velocity,3),path_scale=path_length*deg(.15);
 for(int i=0;i<6;i++){
  double margin=std::min(20.,(limits[i*2+1]-limits[i*2])*.2);
  double low=std::max(0.,1-(q[i]-limits[i*2])/margin),high=std::max(0.,1-(limits[i*2+1]-q[i])/margin);
  bias[i]=path_scale*(low*low-high*high);
 }
 for(int attempt=0;attempt<7;attempt++){
  double rows[6][7]={},result[6];
  double rhs[3];for(int k=0;k<3;k++){rhs[k]=velocity[k]/200.;for(int j=0;j<6;j++)rhs[k]-=jac[k][j]*(active[j]?fixed[j]:bias[j]);}
  for(int i=0;i<6;i++){for(int j=0;j<6;j++){if(!active[i]&&!active[j])for(int k=0;k<3;k++)rows[i][j]+=jac[k][i]*jac[k][j];if(i==j)rows[i][j]+=1e-8;}
   if(!active[i])for(int k=0;k<3;k++)rows[i][6]+=jac[k][i]*rhs[k];}
  if(!linear(rows,result))return 0;bool changed=false;
  for(int i=0;i<6;i++){out[i]=(active[i]?fixed[i]:result[i]+bias[i])*180/PI;
   // Bound outward motion before reaching a hard stop. Re-solve the remaining
   // position Jacobian with that rate fixed; clipping a joint alone changes TCP.
   double lower=-std::max(0.,q[i]-limits[i*2]-.001)*path_length/5.;
   double upper=std::max(0.,limits[i*2+1]-q[i]-.001)*path_length/5.;
   if(!active[i]&&(out[i]<lower||out[i]>upper)){fixed[i]=deg(std::max(lower,std::min(upper,out[i])));active[i]=true;changed=true;}}
  if(!changed)return 1;
 }
 return 0;
}
// Settings: position tolerance, orientation tolerance radians, scale, max step radians, iterations.
// Output: best cost, best q[6], best position/orientation error, iteration count.
static int iterate(const double*g,const double*start,const double*target,const double*limits,const double*settings,double*out,bool position_only){
 double q[6];std::copy(start,start+6,q);double damping=.02,best=std::numeric_limits<double>::infinity();
 out[0]=best;std::copy(q,q+6,out+1);out[7]=out[8]=out[9]=0;
 for(int iteration=0;iteration<int(settings[4]);iteration++){
  double t[16],axes[18],origins[18],e[6];chain(g,q,t,axes,origins,nullptr);residual(t,target,e);
  if(position_only)e[3]=e[4]=e[5]=0;
  double pe=norm(e,3),oe=norm(e+3,3);for(int i=0;i<3;i++)e[i]/=settings[2];
  double cost=0;for(double v:e)cost+=v*v;
  if(!std::isfinite(cost))return -1;
  if(cost<best){best=cost;out[0]=cost;std::copy(q,q+6,out+1);out[7]=pe;out[8]=oe;out[9]=iteration+1;}
  if(pe<=settings[0]&&oe<=settings[1]){std::copy(q,q+6,out+1);return 1;}
  double j[6][6];
  for(int i=0;i<6;i++){
   double p[3]={t[3]-origins[i*3],t[7]-origins[i*3+1],t[11]-origins[i*3+2]},*a=axes+i*3;
   j[0][i]=(a[1]*p[2]-a[2]*p[1])/settings[2];j[1][i]=(a[2]*p[0]-a[0]*p[2])/settings[2];j[2][i]=(a[0]*p[1]-a[1]*p[0])/settings[2];
   for(int k=0;k<3;k++)j[k+3][i]=position_only?0:a[k];
  }
  double rows[6][7]={0},step[6];
  for(int i=0;i<6;i++){
   for(int h=0;h<6;h++)for(int k=0;k<6;k++)rows[i][h]+=j[k][i]*j[k][h];
   for(int k=0;k<6;k++)rows[i][6]+=j[k][i]*e[k];rows[i][i]+=damping*damping;
  }
  if(!linear(rows,step))break;
  double maximum=0;for(double v:step)maximum=std::max(maximum,std::abs(v));
  if(maximum>settings[3])for(double &v:step)v*=settings[3]/maximum;
  bool improved=false;
  for(double scale:{1.,.5,.25,.125,.0625}){
   double candidate[6],trial[6],ct[16],trial_cost=0;
   for(int i=0;i<6;i++)candidate[i]=std::max(limits[i*2],std::min(limits[i*2+1],q[i]+step[i]*180/PI*scale));
   chain(g,candidate,ct,nullptr,nullptr,nullptr);residual(ct,target,trial);
   if(position_only)trial[3]=trial[4]=trial[5]=0;
   for(int i=0;i<3;i++)trial[i]/=settings[2];for(double v:trial)trial_cost+=v*v;
   if(cost-trial_cost>8*std::numeric_limits<double>::epsilon()*cost){std::copy(candidate,candidate+6,q);damping=std::max(1e-5,damping*.7);improved=true;break;}
  }
  if(!improved){damping=std::min(100.,damping*4);if(damping>=100||maximum<1e-10)break;}
 }
 return 0;
}

API int f3p_iterate(const double*g,const double*start,const double*target,const double*limits,const double*settings,double*out){return iterate(g,start,target,limits,settings,out,false);}
API int f3p_position_iterate(const double*g,const double*start,const double*target,const double*limits,const double*settings,double*out){return iterate(g,start,target,limits,settings,out,true);}
