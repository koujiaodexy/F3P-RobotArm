"""Local Wi-Fi and DeepSeek setup window; no robot-control dependencies."""
import json
import os
import pathlib
import socket
import threading
import urllib.error
import uuid

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib


def request_ai(key, model, message):
    import urllib.request
    data=json.dumps(dict(model=model,messages=[dict(role='user',content=message)],
        max_tokens=8192,stream=False,thinking=dict(type='enabled'),reasoning_effort='high')).encode()
    request=urllib.request.Request('https://api.deepseek.com/chat/completions',data=data,
        headers={'Content-Type':'application/json','Authorization':'Bearer '+key},method='POST')
    with urllib.request.urlopen(request,timeout=180) as response:
        result=json.loads(response.read(2*1024*1024).decode())
    return result['choices'][0]['message']['content']


class Setup(Gtk.Window):
    def __init__(self, wifi_only=False, standalone=True):
        super().__init__(title='Wi-Fi / DeepSeek 配置')
        self.set_default_size(760,620)
        self.set_position(Gtk.WindowPosition.CENTER)
        if standalone:self.connect('destroy',Gtk.main_quit)
        self.busy=False
        self.config=pathlib.Path('/home/uisrc/.config/f3p-cloud-ai/deepseek.json')
        self.status_file=self.config.parent/'setup-status.json'
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,margin=20)
        self.add(box)
        box.pack_start(Gtk.Label(label='第一步：连接手机热点。第二步：保存密钥并测试 DeepSeek。',xalign=0),False,False,0)
        self.ssid=self.entry(box,'热点名称','xiaomi14')
        self.password=self.entry(box,'热点密码','',secret=True)
        self.show_password=Gtk.CheckButton(label='显示热点密码')
        self.show_password.connect('toggled',lambda button:self.password.set_visibility(button.get_active()))
        self.show_password.set_active(True)
        box.pack_start(self.show_password,False,False,0)
        self.connect_button=Gtk.Button(label='连接热点')
        self.connect_button.connect('clicked',self.connect_wifi)
        box.pack_start(self.connect_button,False,False,0)
        self.key=self.entry(box,'DeepSeek API 密钥','',secret=True)
        self.show_key=Gtk.CheckButton(label='显示 API 密钥')
        self.show_key.connect('toggled',lambda button:self.key.set_visibility(button.get_active()))
        self.show_key.set_active(True)
        box.pack_start(self.show_key,False,False,0)
        self.model=self.entry(box,'模型名称','deepseek-v4-pro')
        self.message=self.entry(box,'测试文字','请用一句话介绍你能做什么。')
        self.test_button=Gtk.Button(label='保存密钥并测试对话')
        self.test_button.connect('clicked',self.test_ai)
        box.pack_start(self.test_button,False,False,0)
        self.status=Gtk.Label(label='等待输入；本窗口不会控制机械臂。',xalign=0)
        self.status.set_line_wrap(True)
        box.pack_start(self.status,False,False,0)
        scroller=Gtk.ScrolledWindow()
        self.output=Gtk.TextView(editable=False,wrap_mode=Gtk.WrapMode.WORD_CHAR)
        scroller.add(self.output)
        box.pack_start(scroller,True,True,0)
        if self.config.exists() and not wifi_only:
            try:
                value=json.loads(self.config.read_text())
                self.key.set_text(value.get('api_key',''))
                self.model.set_text(value.get('model','deepseek-v4-pro'))
            except (ValueError,OSError):pass

        if wifi_only:
            self.set_title('手机热点连接（修复版）')
            self.set_default_size(680,420)
            box.get_children()[0].set_text('连接成功后，回到原 DeepSeek 窗口测试对话。')
            for widget in [self.key.get_parent(),self.show_key,self.model.get_parent(),self.message.get_parent(),self.test_button]:
                widget.set_no_show_all(True)
                widget.hide()
        self.populate_connected_wifi()

    def populate_connected_wifi(self):
        """Fill the board-local fields without exporting credentials."""
        self._wifi_lookup_closed=False
        self.connect('destroy',lambda *_:setattr(self,'_wifi_lookup_closed',True))
        initial=(self.ssid.get_text(),self.password.get_text())
        threading.Thread(target=self._read_connected_wifi,args=(initial,),daemon=True,name='f3p-wifi-read').start()

    def _read_connected_wifi(self, initial):
        bus=None
        try:
            import dbus
            bus=dbus.SystemBus(private=True);service='org.freedesktop.NetworkManager'
            manager=dbus.Interface(bus.get_object(service,'/org/freedesktop/NetworkManager'),service)
            for device in manager.GetDevices():
                props=dbus.Interface(bus.get_object(service,device),'org.freedesktop.DBus.Properties')
                if int(props.Get(service+'.Device','DeviceType'))!=2 or int(props.Get(service+'.Device','State'))!=100:
                    continue
                active=props.Get(service+'.Device','ActiveConnection')
                active_props=dbus.Interface(bus.get_object(service,active),'org.freedesktop.DBus.Properties')
                path=active_props.Get(service+'.Connection.Active','Connection')
                api=dbus.Interface(bus.get_object(service,path),service+'.Settings.Connection')
                settings=api.GetSettings()
                ssid=bytes(settings['802-11-wireless']['ssid']).decode()
                password=str(api.GetSecrets('802-11-wireless-security')['802-11-wireless-security']['psk'])
                GLib.idle_add(self._apply_connected_wifi,initial,ssid,password)
                break
        except Exception:
            pass

        finally:
            if bus is not None:bus.close()

    def _apply_connected_wifi(self, initial, ssid, password):
        if self._wifi_lookup_closed or self.busy:return False
        keyboard=getattr(self,'_f3p_numeric_keyboard',None)
        if keyboard is not None and keyboard.target in(self.ssid,self.password):return False
        if (self.ssid.get_text(),self.password.get_text())!=initial:return False
        self.ssid.set_text(ssid);self.password.set_text(password)
        self.connect_button.set_label('重新连接热点')
        self.status.set_text('热点已连接；可直接填写或核对 API 密钥，然后测试对话。')
        return False

    @staticmethod
    def entry(box,label,value,secret=False):
        row=Gtk.Box(spacing=12)
        name=Gtk.Label(label=label,xalign=0);name.set_size_request(155,-1)
        field=Gtk.Entry();field.set_text(value);field.set_visibility(not secret)
        if secret:
            field.set_input_purpose(Gtk.InputPurpose.PASSWORD)
            field.set_property('im-module', 'gtk-im-context-simple')
        row.pack_start(name,False,False,0);row.pack_start(field,True,True,0)
        box.pack_start(row,False,False,0)
        return field

    def begin(self,work,message):
        if self.busy:return
        self.busy=True;self.connect_button.set_sensitive(False);self.test_button.set_sensitive(False)
        self.status.set_text(message)
        def run():
            try:result=work()
            except urllib.error.HTTPError as error:
                result={401:'API 密钥无效，请检查。',402:'API 账户余额不足。',429:'请求过于频繁，请稍后再试。'}.get(error.code,'API 返回 HTTP '+str(error.code))
            except urllib.error.URLError:
                result='HTTPS 连接失败，请检查联网、系统时间和证书。'
            except Exception as error:
                error_name=error.get_dbus_name() if hasattr(error,'get_dbus_name') else type(error).__name__
                self.checkpoint(wifi_connected=False,ai_success=False,error_name=error_name)
                result='操作失败：'+error_name
            GLib.idle_add(self.finish,result)
        threading.Thread(target=run,daemon=True).start()

    def finish(self,result):
        self.busy=False;self.connect_button.set_sensitive(True);self.test_button.set_sensitive(True)
        self.status.set_text(result if len(result)<180 else 'DeepSeek 已回复。')
        self.output.get_buffer().set_text(result)
        return False

    def checkpoint(self,**values):
        import time
        self.config.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        values['updated_unix']=time.time()
        temporary=self.status_file.with_suffix('.tmp')
        fd=os.open(str(temporary),os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w') as f:json.dump(values,f)
        os.replace(str(temporary),str(self.status_file))

    def connect_wifi(self,_button):
        ssid=self.ssid.get_text().strip();password=self.password.get_text()
        if not ssid or not password:self.status.set_text('请填写热点名称和密码。');return
        def work():
            import dbus,time
            bus=dbus.SystemBus()
            manager=dbus.Interface(bus.get_object('org.freedesktop.NetworkManager','/org/freedesktop/NetworkManager'),'org.freedesktop.NetworkManager')
            device=None
            for path in manager.GetDevices():
                obj=bus.get_object('org.freedesktop.NetworkManager',path)
                props=dbus.Interface(obj,'org.freedesktop.DBus.Properties')
                if int(props.Get('org.freedesktop.NetworkManager.Device','DeviceType'))==2:
                    device=path;props.Set('org.freedesktop.NetworkManager.Device','Managed',dbus.Boolean(True));break
            if device is None:return '没有找到无线网卡，请先完成驱动检查。'
            manager_props=dbus.Interface(bus.get_object('org.freedesktop.NetworkManager','/org/freedesktop/NetworkManager'),'org.freedesktop.DBus.Properties')
            if not bool(manager_props.Get('org.freedesktop.NetworkManager','NetworkingEnabled')):
                manager.Enable(True)
            dbus.Interface(bus.get_object('org.freedesktop.NetworkManager','/org/freedesktop/NetworkManager'),'org.freedesktop.DBus.Properties').Set('org.freedesktop.NetworkManager','WirelessEnabled',dbus.Boolean(True))
            settings={
                'connection':{'id':'f3p-hotspot-'+ssid,'uuid':str(uuid.uuid4()),'type':'802-11-wireless','autoconnect':True},
                '802-11-wireless':{'ssid':dbus.ByteArray(ssid.encode()),'mode':'infrastructure','security':'802-11-wireless-security','powersave':dbus.Int32(2)},
                '802-11-wireless-security':{'key-mgmt':'wpa-psk','psk':password,'auth-alg':'open','proto':dbus.Array(['rsn'],signature='s'),'pairwise':dbus.Array(['ccmp'],signature='s'),'group':dbus.Array(['ccmp'],signature='s'),'pmf':dbus.Int32(2)},
                'ipv4':{'method':'auto'},'ipv6':{'method':'auto'}}
            settings_api=dbus.Interface(bus.get_object('org.freedesktop.NetworkManager','/org/freedesktop/NetworkManager/Settings'),'org.freedesktop.NetworkManager.Settings')
            # Reuse a matching profile; interface names can change after firmware recovery.
            candidates=[]
            for path in settings_api.ListConnections():
                api=dbus.Interface(bus.get_object('org.freedesktop.NetworkManager',path),'org.freedesktop.NetworkManager.Settings.Connection')
                saved=api.GetSettings()
                if saved.get('connection',{}).get('id')=='f3p-hotspot-'+ssid and bytes(saved.get('802-11-wireless',{}).get('ssid',[]))==ssid.encode():
                    candidates.append((bool(saved['connection'].get('autoconnect',False)),path,api,saved))
            candidates.sort(key=lambda value:value[0],reverse=True)
            if candidates:
                _,connection,api,saved=candidates[0]
                settings['connection']['uuid']=saved['connection']['uuid']
                api.Update(dbus.Dictionary({k:dbus.Dictionary(v,signature='sv') for k,v in settings.items()},signature='sa{sv}'))
            else:
                connection=settings_api.AddConnection(dbus.Dictionary({k:dbus.Dictionary(v,signature='sv') for k,v in settings.items()},signature='sa{sv}'))
            active=manager.ActivateConnection(connection,dbus.ObjectPath(device),dbus.ObjectPath('/'))
            props=dbus.Interface(bus.get_object('org.freedesktop.NetworkManager',device),'org.freedesktop.DBus.Properties')
            started=time.monotonic()
            for _ in range(60):
                state=int(props.Get('org.freedesktop.NetworkManager.Device','State'))
                if state==100:
                    import subprocess
                    subprocess.run(['timedatectl','set-ntp','true'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    self.checkpoint(wifi_connected=True,ssid=ssid,ai_success=False)
                    try:socket.getaddrinfo('api.deepseek.com',443)
                    except socket.gaierror:return '热点已连接，但域名解析失败，请检查手机是否能访问互联网。'
                    return '热点已连接，DeepSeek 域名解析成功。请填写 API 密钥并测试对话。'
                if state==120 or (time.monotonic()-started>5 and state==30):
                    reason=int(props.Get('org.freedesktop.NetworkManager.Device','StateReason')[1])
                    self.checkpoint(wifi_connected=False,ssid=ssid,ai_success=False,network_reason=reason)
                    return '热点连接已中止（网络原因码 '+str(reason)+'），请确认热点仍开启及密码正确。'
                time.sleep(.5)
            return '连接超时，请检查手机热点和信号。'
        self.begin(work,'正在连接 '+ssid+'…')

    def test_ai(self,_button):
        key=self.key.get_text().strip();model=self.model.get_text().strip();message=self.message.get_text().strip()
        if not key or not model or not message:self.status.set_text('请填写 API 密钥、模型名称和测试文字。');return
        def work():
            self.config.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            temporary=self.config.with_suffix('.tmp')
            fd=os.open(str(temporary),os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
            os.fchmod(fd,0o600)
            with os.fdopen(fd,'w') as f:json.dump(dict(api_key=key,model=model),f);f.flush();os.fsync(f.fileno())
            os.replace(str(temporary),str(self.config))
            answer=request_ai(key,model,message)
            self.checkpoint(ai_success=True,model=model,response_characters=len(answer))
            return answer
        self.begin(work,'正在测试 DeepSeek，对话请求按 API 账户计费…')


if __name__=='__main__':
    import sys
    Setup(wifi_only='--wifi-only' in sys.argv).show_all()
    Gtk.main()
