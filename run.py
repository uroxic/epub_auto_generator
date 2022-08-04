import asyncio
import json
from importlib import import_module
from multiprocessing import Pipe, Process

import aiofiles

import server
from make_epub import *

modules = ['dmzj', 'wenku8']


def run_server(pipe_dict, epub_pipe):
    server.pipe_dict = pipe_dict
    server.epub_pipe = epub_pipe
    server.app.run(host="0.0.0.0", port=8000)


def run_epub(r, t):
    loop = asyncio.get_event_loop()
    asyncio.ensure_future(epub_service(r, t))
    loop.run_forever()


async def epub_service(r, t):
    tasks = set()
    while(1):
        if r.poll():
            event = r.recv()
            if (event['action'] == 'generate'):
                temp = await get_state(str(event['module']), str(event['id']))
                if (temp > 2 and temp != 4):
                    try:
                        await update_state(str(event['module']), str(event['id']), 4)
                        task = asyncio.create_task(
                            asyncio.to_thread(make_epub(str(event['module']), str(event['id']), t)))
                        tasks.add(task)
                        task.add_done_callback(tasks.discard)
                    except Exception as e:
                        print(e)
                        await update_state(str(event['module']), str(event['id']), 3)
            elif (event['action'] == 'finish'):
                task = asyncio.create_task(update_state(
                    str(event['module']), str(event['id']), int(event['state'])))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
        else:
            await asyncio.sleep(0.001)


async def get_state(module, id):
    try:
        jsondir = "./" + str(module) + "/novel.json"
        if (os.path.exists(jsondir) == True):
            async with aiofiles.open(jsondir, 'rb') as afp:
                result = (await afp.read()).decode('utf8')
            result = int((json.loads(result))[id]['state'])
            return result
    except Exception as e:
        print(e)
        return 0
    return 0


async def update_state(module, id, state):
    try:
        jsondir = "./" + str(module) + "/novel.json"
        if (os.path.exists(jsondir) == True):
            async with aiofiles.open(jsondir, 'rb') as afp:
                novel_list = (await afp.read()).decode('utf8')
            novel_list = json.loads(novel_list)
            novel_list[id]['state'] = state
            async with aiofiles.open(jsondir, 'wb') as afp:
                json_string = json.dumps(
                    novel_list, ensure_ascii=False).encode('utf8')
                await afp.write(json_string)
    except Exception as e:
        print(e)
        return
    return


def module_luncher(m, r, t):
    loop = asyncio.get_event_loop()
    asyncio.ensure_future(module_service(m, r, t))
    loop.run_forever()


async def add_novel(fetcher, id):
    try:
        fetcher.check_dir(fetcher.save_dir)
        jsondir = fetcher.save_dir[:-4] + "/novel.json"
        if (os.path.exists(jsondir) == True):
            async with aiofiles.open(jsondir, 'rb') as afp:
                novel_list = (await afp.read()).decode('utf8')
            novel_list = json.loads(novel_list)
            if (id not in novel_list.keys()):
                content = await fetcher.get_detail(id)
                novel_list[id] = {}
                novel_list[id]['name'] = content['name']
                novel_list[id]['dir'] = fetcher.correct_dir(content['name'])
                novel_list[id]['cover'] = content['cover']
                novel_list[id]['state'] = 1
                novel_list = dict(
                    sorted(novel_list.items(), key=lambda x: x[0], reverse=False))
                async with aiofiles.open(jsondir, 'wb') as afp:
                    json_string = json.dumps(
                        novel_list, ensure_ascii=False).encode('utf8')
                    await afp.write(json_string)
            else:
                novel_list[id]['state'] = 1
                async with aiofiles.open(jsondir, 'wb') as afp:
                    json_string = json.dumps(
                        novel_list, ensure_ascii=False).encode('utf8')
                    await afp.write(json_string)
        else:
            novel_list = {}
            content = await fetcher.get_detail(id)
            novel_list[id] = {}
            novel_list[id]['name'] = content['name']
            novel_list[id]['dir'] = fetcher.correct_dir(content['name'])
            novel_list[id]['cover'] = content['cover']
            novel_list[id]['state'] = 1
            async with aiofiles.open(jsondir, 'wb') as afp:
                json_string = json.dumps(
                    novel_list, ensure_ascii=False).encode('utf8')
                await afp.write(json_string)
    except Exception as e:
        print(e)
        return
    return


async def module_service(m, r, t):
    locals()[m] = import_module("modules." + m)    # 动态import
    fetcher = locals()[m].fetcher()
    tasks = set()
    while(1):
        if r.poll():
            event = r.recv()
            if (event['action'] == 'add'):
                task = asyncio.create_task(
                    add_novel(fetcher, str(event['id'])))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
            elif (event['action'] == 'refresh'):
                temp = await get_state(str(m), str(event['id']))
                if (temp > 0 and temp != 2 and temp != 4):
                    try:
                        await update_state(str(m), str(event['id']), 2)
                        task = asyncio.create_task(
                            fetcher.get_novel(str(event['id']), t))
                        tasks.add(task)
                        task.add_done_callback(tasks.discard)
                    except Exception as e:
                        print(e)
                        await update_state(str(m), str(event['id']), 1)
            elif (event['action'] == 'finish'):
                task = asyncio.create_task(update_state(
                    str(event['module']), str(event['id']), int(event['state'])))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
        else:
            await asyncio.sleep(0.001)


if __name__ == "__main__":
    ps = []
    epub_pipe = Pipe(duplex=False)
    epub_send = epub_pipe[1]
    epub_recv = epub_pipe[0]
    pipe_dict = {}
    send_list = []
    recv_list = []
    for i in range(len(modules)):
        pipe_dict[modules[i]] = Pipe(duplex=False)  # (read, write)
        send_list.append(pipe_dict[modules[i]][1])
        recv_list.append(pipe_dict[modules[i]][0])
    p = Process(target=run_server, args=(pipe_dict, epub_pipe))
    p.start()
    ps.append(p)
    p = Process(target=run_epub, args=(epub_recv, epub_send))
    p.start()
    ps.append(p)
    for i in range(len(modules)):
        p = Process(target=module_luncher, args=(
            modules[i], recv_list[i], send_list[i]))
        p.start()
        ps.append(p)
    for p in ps:
        p.join()
