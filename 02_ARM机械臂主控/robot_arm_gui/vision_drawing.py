"""Convert exported pixel contours to a sized drawing; no transport access."""
import math
from . import drawing


def is_pixel_document(document):
    return isinstance(document,dict) and 'paths' in document and 'schema' not in document


def contours(document):
    if (not isinstance(document,dict) or type(document.get('version')) is not int
            or document['version']!=1 or document.get('unit')!='px'
            or document.get('origin')!='top-left' or document.get('x_axis')!='right'
            or document.get('y_axis')!='down'):
        raise ValueError('图像路径格式或版本无效')
    def number(value):
        if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):
            raise ValueError('图像路径坐标或尺寸无效')
        return float(value)
    width=number(document.get('width'));height=number(document.get('height'))
    if min(width,height)<=0:raise ValueError('图像尺寸必须大于0')
    paths=document.get('paths')
    if not isinstance(paths,list) or not paths:raise ValueError('图像文件没有可载入的轮廓')
    result=[];count=0
    for path in paths:
        if not isinstance(path,dict) or type(path.get('closed')) is not bool:
            raise ValueError('图像轮廓格式无效')
        points=path.get('points')
        if not isinstance(points,list) or len(points)<2:raise ValueError('图像轮廓至少需要两个点')
        count+=len(points)+2
        if count>drawing.MAX_POINTS:raise ValueError('图像轮廓点数过多，请减少点数后导出')
        vertices=[]
        for point in points:
            if not isinstance(point,list) or len(point)!=2:raise ValueError('图像路径需要二维像素坐标')
            x,y=map(number,point)
            if not 0<=x<=width or not 0<=y<=height:raise ValueError('图像路径坐标超出图片范围')
            if not vertices or [x,y]!=vertices[-1]:vertices.append([x,y])
        if len(vertices)<2:raise ValueError('图像轮廓长度为0')
        result.append((vertices,path['closed']))
    return result


def convert(document,*,size,anchor,axes,flip,settings):
    paths=contours(document)
    if isinstance(size,bool) or not isinstance(size,(int,float)) or not math.isfinite(size) or not .1<=size<=1000:
        raise ValueError('图形最长边须为0.1～1000mm')
    if tuple(sorted(axes))!=(0,1,2):raise ValueError('绘图工作面无效')
    if len(anchor)!=3 or any(not math.isfinite(v) for v in anchor):raise ValueError('图形中心坐标无效')
    vertices=[p for points,_ in paths for p in points]
    lo=[min(p[i] for p in vertices) for i in (0,1)]
    hi=[max(p[i] for p in vertices) for i in (0,1)]
    scale=size/max(hi[i]-lo[i] for i in (0,1))
    center=[(a+b)/2 for a,b in zip(lo,hi)];i,j,_=axes
    out=[]
    for stroke,(points,closed) in enumerate(paths,1):
        xyz=[]
        for x,y in points:
            p=list(anchor);p[i]+=(x-center[0])*scale;p[j]+=(y-center[1])*scale*(1 if flip else -1)
            xyz.append(p)
        out.append(dict(mode='J',xyz=xyz[0],stroke=None))
        out.extend(dict(mode='L',xyz=p,stroke=stroke) for p in xyz)
        if closed and xyz[-1]!=xyz[0]:out.append(dict(mode='L',xyz=list(xyz[0]),stroke=stroke))
    return drawing.validate(dict(settings,schema=1,points=out,allow_orientation_adjustment=False))
