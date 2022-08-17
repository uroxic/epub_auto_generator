import asyncio
import base64
import html
import json
import os
import re
from multiprocessing import Pipe

import aiofiles
import aiohttp
import zhconv
from bs4 import BeautifulSoup
from lxml import etree
from retrying import retry


class fetcher(object):
    def __init__(self, proxy=None):
        self.save_dir = "./wenku8/web"
        self.proxy = proxy
        self.header = [('User-Agent',
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36')]
        self.background_tasks = set()

        # http://app.wenku8.com/android.php
        self.api = "http://app.wenku8.com/android.php"

    @retry(stop_max_attempt_number=3, wait_random_min=200, wait_random_max=600)
    async def download_img(self, url, dir):
        async with aiohttp.ClientSession(headers=self.header) as session:
            async with session.get(url, proxy=self.proxy) as response:
                async with aiofiles.open(dir, 'wb') as afp:
                    await afp.write(await response.content.read())
        return

    def check_dir(self, dir):
        if (os.path.exists(dir) == False):
            os.makedirs(dir)
        return

    def correct_dir(self, dir):
        return (re.sub('([^\u0030-\u0039\u0041-\u007a\u4e00-\u9fa5])', '', dir.strip()))[:31]

    def tag_del(self, tag):
        return tag.has_attr('width') or tag.has_attr('height') or tag.has_attr('style')

    @retry(stop_max_attempt_number=3, wait_random_min=200, wait_random_max=600)
    async def get_detail(self, novel_id):
        temp_header = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36',
                       'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                       'Content-Length': None,
                       'Host': 'app.wenku8.com'}
        req = "action=book&do=info&aid=" + str(novel_id) + "&t=0"
        req = str(base64.b64encode(req.encode('utf8')), 'utf8')
        payload = "request=" + req
        temp_header["Content-Length"] = str(len(payload))
        async with aiohttp.ClientSession(headers=temp_header) as session:
            async with session.post(self.api, data=payload, proxy=self.proxy) as response:
                result = zhconv.convert((await response.content.read()).decode('utf8'), 'zh-cn')
        req = "action=book&do=intro&aid=" + str(novel_id) + "&t=0"
        req = str(base64.b64encode(req.encode('utf8')), 'utf8')
        payload = "request=" + req
        temp_header["Content-Length"] = str(len(payload))
        async with aiohttp.ClientSession(headers=temp_header) as session:
            async with session.post(self.api, data=payload, proxy=self.proxy) as response:
                intro = zhconv.convert((await response.content.read()).decode('utf8'), 'zh-cn')
        soup = BeautifulSoup(result, features='xml')
        detail = {}
        detail['name'] = str(soup.find(name='data', attrs={
                             'name': 'Title'}).contents[0])
        detail['intro'] = str(intro).replace('\r', '\n').replace('\n', '<br/>')
        detail['author'] = str(
            soup.find(name='data', attrs={'name': 'Author'})['value'])
        detail['novel_id'] = int(novel_id)
        detail['cover'] = "http://img.wenku8.com/image/" + \
            str(int(novel_id) // 1000) + "/" + str(novel_id) + \
            "/" + str(novel_id) + "s.jpg"

        return detail

    @retry(stop_max_attempt_number=3, wait_random_min=200, wait_random_max=600)
    async def get_chapter(self, novel_id):
        temp_header = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36',
                       'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                       'Content-Length': None,
                       'Host': 'app.wenku8.com'}
        req = "action=book&do=list&aid=" + str(novel_id) + "&t=0"
        req = str(base64.b64encode(req.encode('utf8')), 'utf8')
        payload = "request=" + req
        temp_header["Content-Length"] = str(len(payload))
        async with aiohttp.ClientSession(headers=temp_header) as session:
            async with session.post(self.api, data=payload, proxy=self.proxy) as response:
                result = zhconv.convert((await response.content.read()).decode('utf8'), 'zh-cn')
        soup = BeautifulSoup(result, features='xml')
        temp = soup.find_all(name=['volume', 'chapter'])
        volume = []
        temp1 = {}
        for i in range(len(temp)):
            if (temp[i].name == 'volume' and (i+1) != len(temp) and temp[i+1].name == 'chapter'):
                if (len(temp1) != 0):
                    volume.append(temp1)
                    temp1 = {}
                temp1['name'] = str(temp[i].contents[0]).replace(
                    '\r', '\n').replace('\n', '')
                temp1['volume_id'] = int(temp[i]['vid'])
                temp1['chapter'] = []
            elif (temp[i].name == 'chapter'):
                temp1['chapter'].append(
                    {"name": str(temp[i].contents[0]).replace('\r', '\n').replace('\n', ''), "chapter_id": int(temp[i]['cid'])})
        if (len(temp1) != 0):
            volume.append(temp1)

        return volume

    @retry(stop_max_attempt_number=3, wait_random_min=200, wait_random_max=600)
    async def get_content(self, novel_id, volume_id, chapter_id):
        temp_header = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36',
                       'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                       'Content-Length': None,
                       'Host': 'app.wenku8.com'}
        req = "action=book&do=text&aid=" + \
            str(novel_id) + "&cid=" + str(chapter_id) + "&t=0"
        req = str(base64.b64encode(req.encode('utf8')), 'utf8')
        payload = "request=" + req
        temp_header["Content-Length"] = str(len(payload))
        async with aiohttp.ClientSession(headers=temp_header) as session:
            async with session.post(self.api, data=payload, proxy=self.proxy) as response:
                result = zhconv.convert((await response.content.read()).decode('utf8'), 'zh-cn').replace(' ', '').replace('\r', '\n').replace('\n', '<br/>').replace('壹', '一').replace('贰', '二').replace('叁', '三')
        content = (html.unescape(result)).replace('\r', '\n').replace('\n', '')
        while(content.find('<br>') != -1):
            content = content.replace('<br>', '<br/>')
        while(content.find('<br/><br/><br/>') != -1):
            content = content.replace('<br/><br/><br/>', '<br/><br/>')
        while(content.find('<!--image-->') != -1):
            content = content.replace('<!--image-->', '<img src="', 1)
            content = content.replace('<!--image-->', '">', 1)
        soup = BeautifulSoup(content, features='lxml')
        imgs = soup.find_all("img")
        tags = soup.find_all(self.tag_del)
        if(len(tags) != 0):
            for i in tags:
                del(i['width'])
                del(i['height'])
                del(i['style'])
        content = soup.prettify("utf-8")

        return content

    def localize_content(self, content, dir):
        soup = BeautifulSoup(content, features='lxml')
        imgs = soup.find_all(name='div', class_='divimage')
        if(len(imgs) != 0):
            for i in imgs:
                i.replace_with(i.contents[1].contents[1])
        imgs = soup.find_all('img')
        if(len(imgs) != 0):
            for i in imgs:
                temp = list(i.attrs.keys())
                for j in temp:
                    if(j != 'src' and j != 'class'):
                        del(i[j])
                url = str(i['src'])
                img_name = list(url.split('/'))[-1]
                self.check_dir(dir + '/img')
                task = asyncio.create_task(
                    self.download_img(url, dir + '/img/' + img_name))
                self.background_tasks.add(task)
                task.add_done_callback(self.background_tasks.discard)
                i['src'] = 'img/' + img_name
            content = soup.prettify("utf-8")
        return content

    async def content_lost(self, chapter_dir):
        try:
            if (os.path.exists(chapter_dir + '/' + 'text.htm') == False):
                return True
            async with aiofiles.open(chapter_dir + '/' + 'text.htm', 'rb') as afp:
                content = (await afp.read()).decode('utf8')
                soup = BeautifulSoup(content, features='lxml')
                imgs = soup.find_all('img')
                if(len(imgs) != 0):
                    for i in imgs:
                        if (os.path.exists(chapter_dir + '/' + str(i['src'])) == False):
                            return True
                return False
        except:
            return True

    async def get_novel(self, novel_id, t, lazy=True):
        try:
            info = await self.get_detail(novel_id)
            volume = await self.get_chapter(novel_id)
            novel_dir = self.save_dir + '/' + self.correct_dir(info['name'])
            self.check_dir(novel_dir)
            if((lazy == False) or (os.path.exists(novel_dir + '/' + 'cover.jpg') == False)):
                task = asyncio.create_task(
                    self.download_img(info['cover'], novel_dir + '/' + 'cover.jpg'))
                self.background_tasks.add(task)
                task.add_done_callback(self.background_tasks.discard)
            for i in volume:
                volume_dir = novel_dir + '/' + \
                    self.correct_dir(str(i['volume_id']) + i['name'])
                self.check_dir(volume_dir)
                for j in i['chapter']:
                    chapter_dir = volume_dir + '/' + \
                        self.correct_dir(str(j['chapter_id']) + j['name'])
                    self.check_dir(chapter_dir)
                    if((lazy == False) or ((await self.content_lost(chapter_dir)) == True)):
                        content = await self.get_content(
                            info['novel_id'], i['volume_id'], j['chapter_id'])
                        content = self.localize_content(content, chapter_dir)
                        async with aiofiles.open(chapter_dir + '/' + 'text.htm', 'wb') as afp:
                            await afp.write(content)
            async with aiofiles.open(novel_dir + '/' + 'info.json', 'wb') as afp:
                json_string = json.dumps(
                    info, ensure_ascii=False).encode('utf8')
                await afp.write(json_string)
            async with aiofiles.open(novel_dir + '/' + 'volume.json', 'wb') as afp:
                json_string = json.dumps(
                    volume, ensure_ascii=False).encode('utf8')
                await afp.write(json_string)
            try:
                await asyncio.wait(self.background_tasks)
            except:
                pass
            t.send({'action': 'finish', 'id': novel_id,
                   'module': 'wenku8', 'state': 3})
        except Exception as e:
            print(e)
            try:
                await asyncio.wait(self.background_tasks)
            except:
                pass
            t.send({'action': 'finish', 'id': novel_id,
                   'module': 'wenku8', 'state': 1})
            return
        return
