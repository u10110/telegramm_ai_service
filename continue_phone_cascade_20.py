from __future__ import annotations
import asyncio, csv, json, os
from pathlib import Path
from _config import _load_env_file
_load_env_file(Path('/root/leadgen_restore'))
from telethon import TelegramClient, functions, types
from telethon.errors import PhoneNotOccupiedError, FloodWaitError

PATH = Path('/root/.hermes/profiles/aibomber/cache/documents/telegram_numbers_1000_no_800_with_status_checked_corrected.csv')
BATCH = 20

def save(rows, fields):
    tmp = PATH.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)
    tmp.replace(PATH)

def proxy():
    import python_socks
    return {'proxy_type': python_socks.ProxyType.SOCKS5,
            'addr': os.getenv('TELEGRAM_PROXY_ADDR', 'sing-box'),
            'port': int(os.getenv('TELEGRAM_PROXY_PORT', '10808')), 'rdns': True}

async def main():
    with PATH.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    fields = list(rows[0])
    pending = [i for i, r in enumerate(rows) if r.get('telegram_status') in ('', 'not_checked')]
    client = TelegramClient(os.getenv('TELEGRAM_SESSION', '/root/leadgen_restore/telegram_userbot.session'),
                            int(os.environ['TELEGRAM_API_ID']), os.environ['TELEGRAM_API_HASH'],
                            proxy=proxy(), connection_retries=2, request_retries=1)
    await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError('Telegram session is not authorized')
    processed = 0
    stop = None
    for batch_start in range(0, len(pending), BATCH):
        batch = pending[batch_start:batch_start+BATCH]
        batch_results = []
        for idx in batch:
            row = rows[idx]
            phone = ''.join(ch for ch in str(row.get('phone', '')) if ch.isdigit())
            try:
                method = 'import_contacts'
                try:
                    contact = types.InputPhoneContact(client_id=idx, phone='+' + phone, first_name='Lead', last_name='Check')
                    imported = await asyncio.wait_for(client(functions.contacts.ImportContactsRequest([contact])), 30)
                    users = imported.users or []
                except PhoneNotOccupiedError:
                    users = []
                if not users:
                    method = 'resolve_phone'
                    try:
                        resolved = await asyncio.wait_for(client(functions.contacts.ResolvePhoneRequest('+' + phone)), 30)
                        users = getattr(resolved, 'users', None) or []
                    except PhoneNotOccupiedError:
                        users = []
                if not users:
                    method = 'get_entity'
                    try:
                        entity = await asyncio.wait_for(client.get_entity('+' + phone), 30)
                        users = [entity] if getattr(entity, 'id', None) else []
                    except Exception:
                        users = []
                if users:
                    u = users[0]
                    row.update(telegram_status='present', check_note=f'Найдено через {method}; сообщение не отправлялось',
                               telegram_user_id=str(getattr(u, 'id', '') or ''),
                               telegram_username=getattr(u, 'username', '') or '',
                               telegram_first_name=getattr(u, 'first_name', '') or '',
                               telegram_last_name=getattr(u, 'last_name', '') or '')
                    status = 'present'
                    try:
                        if getattr(u, 'access_hash', None):
                            await client(functions.contacts.DeleteContactsRequest(id=[types.InputUser(user_id=u.id, access_hash=u.access_hash)]))
                    except Exception:
                        pass
                else:
                    row.update(telegram_status='absent', check_note=f'Не найдено через ImportContactsRequest, ResolvePhoneRequest и get_entity; сообщение не отправлялось')
                    status = 'absent'
            except FloodWaitError as e:
                seconds = int(getattr(e, 'seconds', 60))
                row.update(telegram_status='not_checked', check_note=f'FloodWait {seconds}s; дальнейшая проверка остановлена')
                save(rows, fields)
                stop = {'ordinal': idx + 1, 'flood_wait_seconds': seconds, 'processed_this_run': processed}
                print(json.dumps(stop, ensure_ascii=False), flush=True)
                break
            except Exception as e:
                row.update(telegram_status='error', check_note=f'{type(e).__name__}: {e}'[:300])
                status = 'error'
            processed += 1
            batch_results.append({'ordinal': idx + 1, 'status': status})
            await asyncio.sleep(2)
        save(rows, fields)
        print(json.dumps({'batch_done': len(batch_results), 'batch_start_ordinal': batch[0] + 1,
                          'batch_end_ordinal': (batch[len(batch_results)-1] + 1) if batch_results else batch[0] + 1,
                          'processed_this_run': processed}, ensure_ascii=False), flush=True)
        if stop:
            break
    await client.disconnect()
    print(json.dumps({'done_without_flood': stop is None, 'processed_this_run': processed,
                      'flood': stop, 'output': str(PATH)}, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    asyncio.run(main())
