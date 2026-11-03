"""DeepSeek tool conversations with real results and complete reasoning metadata."""
import copy
import contextvars
import time
import math
import urllib.error
import json
from .ai_arm_control import tools, validate_action
from .ai_ui_control import ui_tools, validate_ui_action

DEFAULT_MODEL='deepseek-v4-pro'
MAX_ROUNDS=12
_OPTIONS=contextvars.ContextVar('ai_reply_options',default={})

class ReplyError(ValueError):
    pass

class ConversationFailure(Exception):
    def __init__(self,cause,history,completed_tools):
        super().__init__(type(cause).__name__)
        self.cause=cause;self.history=copy.deepcopy(history);self.completed_tools=completed_tools

def compact_state(value):
    if isinstance(value,float) and not math.isfinite(value):return None
    if isinstance(value,(list,tuple)):return [compact_state(v) for v in value]
    if not isinstance(value,dict):return value
    result={k:compact_state(v) for k,v in value.items()}
    if isinstance(value.get('points'),list):
        result['point_count']=len(value['points']);result['points']=copy.deepcopy(value['points'][:8])
        result['points_preview_only']=len(value['points'])>8
    if isinstance(value.get('teaching_poses'),list):
        result['teaching_pose_count']=len(value['teaching_poses']);result['teaching_poses']=copy.deepcopy(value['teaching_poses'][-8:])
    return result

def recent_history(messages,max_turns=4,max_chars=48000):
    # Cut only at user turn boundaries, never inside assistant/tool sequences.
    starts=[i for i,m in enumerate(messages) if m.get('role')=='user']
    if not starts:return copy.deepcopy(messages)
    first=starts[max(0,len(starts)-max_turns)]
    while len(json.dumps(messages[first:],ensure_ascii=False))>max_chars:
        later=[i for i in starts if i>first]
        if not later:break
        first=later[0]
    return copy.deepcopy(messages[first:])

def error_text(error):
    cause=error.cause if isinstance(error,ConversationFailure) else error
    if isinstance(cause,urllib.error.HTTPError):
        text={401:'API密钥无效',402:'API账户余额不足',429:'请求频率过高'}.get(cause.code,'API返回HTTP %d'%cause.code)
    elif isinstance(cause,(urllib.error.URLError,TimeoutError)):text='网络连接失败或超时'
    elif isinstance(cause,ReplyError):text=str(cause)
    else:text='回复处理异常（%s）'%type(cause).__name__
    if isinstance(error,ConversationFailure) and error.completed_tools:
        text+='；已保留%d项工具结果，请核对本地结果，勿直接重复运动指令'%error.completed_tools
    return text



def parse_action(call):
    if not isinstance(call,dict) or call.get('type')!='function':raise ValueError('动作格式无效')
    fn=call['function']
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('重复动作参数')
            result[key]=value
        return result
    args=json.loads(fn['arguments'],object_pairs_hook=unique)
    validator=validate_ui_action if fn['name'] in {t['function']['name'] for t in ui_tools()} else validate_action
    return validator(fn['name'],args)


def completion(key, model, messages, with_tools=True):
    import urllib.request
    options=_OPTIONS.get();fast=options.get('mode')=='fast'
    payload=dict(model=model,messages=messages,max_tokens=4096 if fast else 16384,stream=False,
                 thinking=dict(type='disabled' if fast else 'enabled'))
    if not fast:payload['reasoning_effort']='high'
    progress=options.get('progress')
    if progress:progress('正在等待云端回复（'+('快速' if fast else '深度思考')+'）…')
    began=time.monotonic()
    if with_tools:payload.update(tools=tools()+ui_tools(),tool_choice='auto')
    request=urllib.request.Request('https://api.deepseek.com/chat/completions',
        data=json.dumps(payload,allow_nan=False).encode(),
        headers={'Content-Type':'application/json','Authorization':'Bearer '+key},method='POST')
    with urllib.request.urlopen(request,timeout=180) as response:
        raw=response.read(4*1024*1024+1)
    if len(raw)>4*1024*1024:raise ReplyError('AI回复过大')
    try:
        value=json.loads(raw.decode('utf-8'));choice=value['choices'][0]
        message=choice['message']
    except (ValueError,KeyError,IndexError,TypeError,UnicodeError) as exc:
        raise ReplyError('云端返回的回复格式无效') from exc
    if not isinstance(message,dict):raise ReplyError('云端回复消息格式无效')
    print('AI_REPLY_RECEIVED',json.dumps(dict(seconds=round(time.monotonic()-began,3),mode='fast' if fast else 'deep',finish_reason=choice.get('finish_reason'),tool_count=len(message.get('tool_calls') or []) if isinstance(message.get('tool_calls') or [],list) else -1)),flush=True)
    if choice.get('finish_reason')=='length':raise ReplyError('AI输出达到上限，请减少曲线采样点或切换深度思考模式')
    if not isinstance(message.get('content') or '',str):raise ReplyError('云端回复正文类型无效')
    return {k:v for k,v in message.items() if k in ('role','content','reasoning_content','tool_calls')}


def conversation(key, model, messages, run_tool, cancelled=lambda:False, mode='deep', progress=None):
    token=_OPTIONS.set(dict(mode=mode,progress=progress))
    try:return _conversation(key,model,messages,run_tool,cancelled,progress)
    finally:_OPTIONS.reset(token)

def _conversation(key,model,messages,run_tool,cancelled,progress):
    history=copy.deepcopy(messages);completed_tools=0
    for _ in range(MAX_ROUNDS):
        if cancelled():return dict(text='本轮已停止，后续操作已取消；停止是否完成请查看本地反馈。',action=None,history=history)
        try:
            message=completion(key,model,history)
        except Exception as exc:
            raise ConversationFailure(exc,history,completed_tools) from exc
        calls=message.get('tool_calls') or []
        if not calls:
            text=message.get('content') or ''
            if not text.strip():raise ConversationFailure(ReplyError('云端回复为空'),history,completed_tools)
            history.append(message)
            return dict(text=text,action=None,history=history)
        if not isinstance(calls,list) or len(calls)>16:raise ConversationFailure(ReplyError('工具调用数量无效'),history,completed_tools)
        if any(not isinstance(c,dict) for c in calls):raise ConversationFailure(ReplyError('工具调用格式无效'),history,completed_tools)
        ids=[c.get('id') for c in calls]
        if any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids):
            raise ConversationFailure(ReplyError('工具调用标识无效'),history,completed_tools)
        history.append(message)
        # Each tool runs to its local completion before the next tool starts.
        for call in calls:
            try:
                action=parse_action(call)
                if progress:progress('本地正在处理：'+action['name']+'…')
                result=(dict(ok=False,error='本轮已取消') if cancelled() else run_tool(action))
            except Exception as exc:
                result=dict(ok=False,error=str(exc))
            history.append(dict(role='tool',tool_call_id=call['id'],
                content=json.dumps(compact_state(result),ensure_ascii=False,allow_nan=False)))
            completed_tools+=1
    return dict(text='已达到本轮工具调用上限，请查看控制结果后继续下达指令。',action=None,history=history)
