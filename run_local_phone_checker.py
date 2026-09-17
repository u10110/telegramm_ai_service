from __future__ import annotations
import asyncio, csv, json, os, shutil
from pathlib import Path
from _config import _load_env_file
_load_env_file(Path('/root/leadgen_restore'))
from telethon import TelegramClient, functions, types
from telethon.errors import PhoneNotOccupiedError, FloodWaitError, RPCError

BASE=Path('/root/.hermes/profiles/aibomber/cache/documents')
SRC=BASE/'telegram_numbers_1000_no_800_with_status.csv'
OUT=BASE/'telegram_numbers_1000_no_800_with_status_checked.csv'
CHECKPOINT=BASE/'.telegram_numbers_checkpoint.json'
SESSION=Path('/root/leadgen_restore/telegram_userbot.session')
FIELDS=['phone','operator','region','territory','inn','source_prefix','source_from','source_to','telegram_status','check_note','telegram_user_id','telegram_username','telegram_first_name','telegram_last_name','telegram_bio','telegram_is_bot','telegram_is_verified','telegram_is_premium','telegram_is_scam','telegram_is_fake','telegram_restricted','telegram_language_code','telegram_profile_error','telegram_avatar_present','telegram_avatar_path','telegram_avatar_error']

def load_rows():
    base=OUT if OUT.exists() else SRC
    with base.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
    for r in rows:
        for k in FIELDS: r.setdefault(k,'')
        if not r.get('phone') or '*' in r['phone']:
            p=''.join(c for c in str(r.get('source_prefix','')) if c.isdigit())
            n=''.join(c for c in str(r.get('source_from','')) if c.isdigit())
            r['phone']='+7'+p+n.zfill(7)
    return rows

def save(rows, note=''):
    tmp=OUT.with_suffix('.tmp')
    with tmp.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    tmp.replace(OUT)

def proxy():
    import python_socks
    return {'proxy_type':python_socks.ProxyType.SOCKS5,'addr':os.getenv('TELEGRAM_PROXY_ADDR','sing-box'),'port':int(os.getenv('TELEGRAM_PROXY_PORT','10808')),'rdns':True}

def apply_user(r,u):
    r.update({'telegram_status':'present','check_note':'Telegram вернул peer; сообщение не отправлялось','telegram_user_id':str(getattr(u,'id','') or ''),'telegram_username':getattr(u,'username','') or '','telegram_first_name':getattr(u,'first_name','') or '','telegram_last_name':getattr(u,'last_name','') or '','telegram_bio':getattr(u,'about','') or '','telegram_is_bot':str(bool(getattr(u,'bot',False))).lower(),'telegram_is_verified':str(bool(getattr(u,'verified',False))).lower(),'telegram_is_premium':str(bool(getattr(u,'premium',False))).lower(),'telegram_is_scam':str(bool(getattr(u,'scam',False))).lower(),'telegram_is_fake':str(bool(getattr(u,'fake',False))).lower(),'telegram_restricted':str(bool(getattr(u,'restricted',False))).lower(),'telegram_language_code':getattr(u,'lang_code','') or ''})

async def main():
    rows=load_rows(); todo=[(i,r) for i,r in enumerate(rows) if r.get('telegram_status') in ('','not_checked')]
    client=TelegramClient(str(SESSION),int(os.environ['TELEGRAM_API_ID']),os.environ['TELEGRAM_API_HASH'],proxy=proxy(),connection_retries=2,request_retries=1)
    await client.connect()
    if not await client.is_user_authorized(): raise RuntimeError('Telegram session is not authorized')
    stats={'total':len(rows),'pending_start':len(todo),'checked':0,'present':0,'absent':0,'errors':0,'batches':0}
    for start in range(0,len(todo),10):
        batch=todo[start:start+10]; stats['batches']+=1
        for i,r in batch:
            phone=''.join(c for c in str(r['phone']) if c.isdigit())
            if len(phone)!=11: r.update({'telegram_status':'not_checked','check_note':'invalid phone format'}); continue
            try:
                contact=types.InputPhoneContact(client_id=0,phone='+'+phone,first_name='Lead',last_name='Check')
                imported=None
                while True:
                    try:
                        imported=await asyncio.wait_for(client(functions.contacts.ImportContactsRequest([contact])),timeout=25)
                        break
                    except FloodWaitError as e:
                        wait_seconds=int(getattr(e,'seconds',60)); save(rows)
                        print(json.dumps({'method':'import_contacts','flood_wait_seconds':wait_seconds,'checked':stats['checked']},ensure_ascii=False),flush=True)
                        await asyncio.sleep(wait_seconds + 3)
                users=imported.users or []
                method='import_contacts'
                if not users:
                    resolved=await asyncio.wait_for(client(functions.contacts.ResolvePhoneRequest('+'+phone)),timeout=25)
                    users=getattr(resolved,'users',None) or []
                    method='resolve_phone'
                if not users:
                    try:
                        entity=await asyncio.wait_for(client.get_entity('+'+phone),timeout=25)
                        users=[entity] if getattr(entity,'id',None) else []
                        method='get_entity'
                    except Exception:
                        users=[]
                if users:
                    apply_user(r,users[0]); r['check_note']=f'Найдено через {method}; сообщение не отправлялось'; stats['present']+=1
                    try:
                        u=users[0]
                        if getattr(u,'access_hash',None): await client(functions.contacts.DeleteContactsRequest(id=[types.InputUser(user_id=u.id,access_hash=u.access_hash)]))
                    except Exception: pass
                else:
                    r.update({'telegram_status':'absent','check_note':'Не найдено ImportContactsRequest, ResolvePhoneRequest и get_entity; сообщение не отправлялось'}); stats['absent']+=1
            except PhoneNotOccupiedError:
                r.update({'telegram_status':'absent','check_note':'PhoneNotOccupiedError; сообщение не отправлялось'}); stats['absent']+=1
            except FloodWaitError as e:
                wait_seconds=int(getattr(e,'seconds',60)); r.update({'telegram_status':'not_checked','check_note':f'FloodWait {wait_seconds}s в резервном методе; проверка не завершена'}); save(rows); print(json.dumps({'method':'fallback','flood_wait_seconds':wait_seconds,'checked':stats['checked']},ensure_ascii=False),flush=True); break
            except Exception as e:
                r.update({'telegram_status':'error','check_note':f'{type(e).__name__}: {e}'[:300]}); stats['errors']+=1
            stats['checked']+=1
            await asyncio.sleep(1.5)
        save(rows)
        CHECKPOINT.write_text(json.dumps({'processed':start+len(batch),'stats':stats},ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'checkpoint':start+len(batch),**stats},ensure_ascii=False),flush=True)
    await client.disconnect(); save(rows)
    print(json.dumps({'done':True,**stats},ensure_ascii=False))

if __name__=='__main__': asyncio.run(main())
