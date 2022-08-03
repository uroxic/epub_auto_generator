import json
import re
from multiprocessing import Pipe

import aiofiles
from jinja2 import Environment, PackageLoader, Template
from sanic import Sanic, html
from sanic.response import file, redirect

env = Environment(loader=PackageLoader(
    'templates', ''))    # 创建一个包加载器对象

index = env.get_template('index.html')    # 获取一个模板文件
mods = env.get_template('mods.html')    # 获取一个模板文件

pipe_dict = {}
epub_pipe = None
app = Sanic('epub_auto_gen')


def correct_dir(dir):
    return re.sub('([^\u0030-\u0039\u0041-\u007a\u4e00-\u9fa5])', '', dir.strip())


@ app.route("/")
async def main_func(request):
    modules = list(pipe_dict.keys())
    ret = index.render(content=modules)   # 渲染
    return html(ret)


@ app.route("/mods/<module:str>/<page:int>", methods=["GET", "POST"])
async def module_func(request, module, page):
    try:
        success = 1
        novel_list = {}
        req = {}
        pages = []
        modules = list(pipe_dict.keys())
        if (request.json and request.json["action"] == "add"):
            req["action"] = request.json["action"]
            req["id"] = request.json["id"]
            pipe_dict[str(module)][1].send(req)
        elif (request.json and request.json["action"] == "refresh"):
            req["action"] = request.json["action"]
            req["id"] = request.json["id"]
            pipe_dict[str(module)][1].send(req)
        elif (request.json and request.json["action"] == "generate"):
            req["action"] = request.json["action"]
            req["module"] = str(module)
            req["id"] = request.json["id"]
            epub_pipe[1].send(req)
            # pipe_dict[modules[0]][1].send({'action': 'refresh', 'id': 2909})
        else:
            try:
                jsondir = "./" + module + "/novel.json"
                async with aiofiles.open(jsondir, 'rb') as afp:
                    temp = (await afp.read()).decode('utf8')
                temp = json.loads(temp)
                ids = list(temp.keys())
                total_pages = int((len(ids) + 11) // 12)
                if (page > 0 and page <= total_pages):
                    for k in ids[((page-1) * 12): (page * 12)]:
                        novel_list[k] = temp[k]
                    for i in range(max(1, (page-2)), min(total_pages+1, (page+3))):
                        pages.append(int(i))
                    success = 1
                else:
                    success = 0
            except Exception as e:
                print(e)
                success = 0
        ret = mods.render(
            content={"module": module, "success": success, "curr_page": int(page), "pages": pages, "novel_list": novel_list})   # 渲染
        return html(ret)
    except Exception as e:
        print(e)
        return html("<b>File Not Found</b>")


@ app.route("/download/<module:str>/<id:int>")
async def download_func(request, module, id):
    try:
        jsondir = "./" + module + "/novel.json"
        async with aiofiles.open(jsondir, 'rb') as afp:
            novel_list = (await afp.read()).decode('utf8')
        novel_list = json.loads(novel_list)
        file_name = novel_list[str(id)]["dir"]
        return await file("./" + str(module) + "/epub/" + str(file_name) + ".epub", mime_type="application/epub+zip")
    except Exception as e:
        print(e)
        return html("<b>File Not Found</b>")


@app.route("/static/<foo:path>")
async def static_func0(request, foo: str):
    try:
        return await file("./templates/static/" + foo)
    except Exception as e:
        print(e)
        return html("<b>File Not Found</b>")


@app.route("<nothing:path>/static/<foo:path>")
async def static_func1(request, nothing: str, foo: str):
    try:
        return await file("./templates/static/" + foo)
    except Exception as e:
        print(e)
        return html("<b>File Not Found</b>")


@app.route("/templates/<foo:path>")
async def templates_func(request, foo: str):
    try:
        return await file("./templates/" + foo)
    except Exception as e:
        print(e)
        return html("<b>File Not Found</b>")
