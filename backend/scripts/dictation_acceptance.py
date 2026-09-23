"""Browser acceptance with simulated transcripts and real petition HTTP workflow."""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

root=Path(__file__).resolve().parents[1]
env={**os.environ,'DATA_DIR':tempfile.mkdtemp(prefix='manual-dictation-'),'LLM_PROVIDER':'off','ALLOW_EXTERNAL_AI':'false','PDF_ENGINE':'off','STREAM_ASR_PROVIDER':'off','TTS_PROVIDER':'off','KNOWLEDGE_ENABLED':'false'}
url='http://127.0.0.1:8024'
out=root.parent/'artifacts'/'dictation';out.mkdir(parents=True,exist_ok=True)
mock=r'''
window.audioInstances=[];
window.Audio=class {constructor(url){this.src=url;window.audioInstances.push(this);}play(){return Promise.resolve();}pause(){}load(){}removeAttribute(){}};
const nativeMic=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
navigator.mediaDevices.getUserMedia=async options=>{window.micOptions=options;if(window.denyMic)throw new DOMException('denied','NotAllowedError');window.micCalls=(window.micCalls||0)+1;return nativeMic(options);};
window.sockets=[];
window.WebSocket=class {constructor(url){this.url=url;this.readyState=1;this.bufferedAmount=0;this.sent=[];window.sockets.push(this);setTimeout(()=>this.emit({type:'dictation.ready',sample_rate:16000}),20);}emit(data){this.onmessage?.({data:JSON.stringify(data)});}send(data){if(typeof data==='string')this.sent.push(JSON.parse(data));}close(){this.readyState=3;} };
'''
with (out/'server.log').open('w') as log:
 server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8024'],cwd=root,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 try:
  for _ in range(100):
   try:
    if httpx.get(url+'/api/health').status_code==200:break
   except httpx.ConnectError:pass
   time.sleep(.1)
  with sync_playwright() as p:
   browser=p.chromium.launch(args=['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--autoplay-policy=no-user-gesture-required'])
   context=browser.new_context(permissions=['microphone'],viewport={'width':1440,'height':1000})
   context.add_init_script(mock)
   page=context.new_page();errors=[];messages=[]
   page.on('pageerror',lambda e:errors.append(str(e)))
   page.on('request',lambda r:messages.append(r.post_data_json) if r.url.endswith('/message') else None)
   page.route('**/speech',lambda route:route.fulfill(status=200,body=b'test audio',content_type='audio/wav'))
   def emit(kind,text='',segment='1'):
    page.evaluate('(m)=>window.sockets.at(-1).emit(m)',{'type':kind,'text':text,'segment':segment})
   def end_tts():
    page.wait_for_function('typing.speaking && window.audioInstances.length>0')
    page.evaluate('window.audioInstances.at(-1).onended()')
    expect(page.locator('#micInline')).to_be_enabled()
   page.goto(url+'/#create')
   expect(page.locator('.turn.assistant')).to_have_count(1)
   page.wait_for_function('window.audioInstances.length===1')
   expect(page.locator('#micInline')).to_be_disabled()
   assert page.evaluate('window.micCalls||0')==0
   assert page.locator('#voiceBar,#dictation,#answerCheck').count()==0
   end_tts()
   page.locator('#micInline').click();expect(page.locator('#micInline')).to_have_attribute('aria-label','Stop dictation')
   assert page.evaluate('window.micOptions.audio.noiseSuppression') is True
   emit('stt.partial','Ravi');expect(page.locator('#text')).to_have_value('Ravi')
   emit('stt.partial','Ravi K');expect(page.locator('#text')).to_have_value('Ravi K')
   emit('stt.final','Ravi Kumar');emit('stt.final','Ravi Kumar');expect(page.locator('#text')).to_have_value('Ravi Kumar')
   assert not messages
   page.locator('#micInline').click();assert page.evaluate('typing.stream===null')
   emit('dictation.stopped');expect(page.locator('#text')).to_have_value('Ravi Kumar')
   page.locator('#text').fill('Ravi Kumaran');emit('stt.final','WRONG LATE RESULT','2');expect(page.locator('#text')).to_have_value('Ravi Kumaran')
   page.locator('#send').click();page.wait_for_function('view.awaiting==="age"');assert messages[-1]['text']=='Ravi Kumaran'
   end_tts();assert page.evaluate('window.micCalls')==1
   # Append, mixed languages, edits during finalization, failure preservation.
   page.locator('#text').fill('Already corporation office la')
   page.locator('#micInline').click();page.wait_for_function('typing.phase==="recording"')
   emit('stt.partial','complaint');emit('stt.final','complaint panniten.');page.locator('#micInline').click()
   page.locator('#text').fill('Manually corrected answer');emit('stt.final','late overwrite','3');expect(page.locator('#text')).to_have_value('Manually corrected answer')
   page.evaluate('window.denyMic=true');page.locator('#micInline').click();expect(page.locator('#dictationStatus')).to_contain_text('Microphone access');expect(page.locator('#text')).to_have_value('Manually corrected answer')
   page.evaluate('window.denyMic=false');page.locator('#micInline').click();page.wait_for_function('typing.phase==="recording"');emit('stt.partial','retained words');emit('error');expect(page.locator('#text')).to_have_value('Manually corrected answer retained words')
   assert len(messages)==1
   # Existing text workflow still reaches attachment/review/generation.
   for value in ['45','9876543210','12 Gandhi Street, Coimbatore']:
    page.locator('#text').fill(value);page.locator('#send').click();page.wait_for_function('!requestPending && !busy');end_tts()
   assert page.evaluate('view.awaiting')=='grievance'
   page.locator('#text').fill('No water supply for five days.')
   page.locator('#micInline').click();page.wait_for_function('typing.phase==="recording"')
   # A full minute of sequential live results; no send or silence-triggered transition.
   for n in range(30):
    emit('stt.partial',f'I reported incident {n}.',str(n))
    emit('stt.final',f'I reported incident {n}.',str(n))
    page.wait_for_timeout(2000)
   expect(page.locator('#micInline')).to_have_attribute('aria-pressed','true')
   assert len(messages)==4
   page.locator('#micInline').click();emit('dictation.stopped')
   before=page.locator('#text').input_value()
   page.locator('#micInline').click();page.wait_for_function('typing.phase==="recording"');emit('stt.final','Please restore the water supply.','0');page.locator('#micInline').click();emit('dictation.stopped')
   assert page.locator('#text').input_value()==before+' Please restore the water supply.'
   page.screenshot(path=str(out/'english-review-before-send.png'),full_page=True)
   page.locator('#send').click();page.wait_for_function('!busy && !requestPending');end_tts()
   if page.evaluate('view.status')=='attachments':
    page.locator('#confirm').click();page.wait_for_function('view.status==="confirming"');end_tts()
   assert page.evaluate('view.status')=='confirming'
   page.locator('#confirm').click();page.wait_for_function('view.status==="ready"',timeout=60000)
   # Tamil input and responsive screen on a separate fresh session.
   page.evaluate('stopPlayback()');page.locator('#lang').select_option('ta');page.wait_for_function('lang==="ta"')
   page.evaluate('typing.responses=false;paintVoice()')
   page.locator('#text').fill('')
   page.locator('#micInline').click();page.wait_for_function('typing.phase==="recording"')
   emit('stt.partial','எங்கள் பகுதியில்');emit('stt.final','எங்கள் பகுதியில் மூன்று நாட்களாக தண்ணீர் வரவில்லை.')
   expect(page.locator('#text')).to_have_value('எங்கள் பகுதியில் மூன்று நாட்களாக தண்ணீர் வரவில்லை.')
   page.screenshot(path=str(out/'tamil-listening.png'),full_page=True)
   page.set_viewport_size({'width':390,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');page.screenshot(path=str(out/'mobile-listening.png'),full_page=True)
   assert not errors,errors
   browser.close()
  print('PASS: manual mic, partial/final deduplication, append, edits, errors, TTS gating, no auto-send, 60-second grievance, Tamil/mixed text, existing workflow generation, mobile')
 finally:
  server.terminate();server.wait(timeout=15)
