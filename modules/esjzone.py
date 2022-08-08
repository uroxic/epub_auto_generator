import asyncio
import html
import json
import os
import re
import urllib.parse
from multiprocessing import Pipe

import aiofiles
import aiohttp
import zhconv
from bs4 import BeautifulSoup
from lxml import etree
from retrying import retry


class fetcher(object):
    def __init__(self, proxy=None):
        self.save_dir = "./esjzone/web"
        self.proxy = proxy
        self.header = [('User-Agent',
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36')]
        self.cookie = {}
        self.email = ""
        self.password = ""
        self.background_tasks = set()

        # https://www.esjzone.net/detail/{novel_id}.html
        self.detail_api = "https://www.esjzone.net/detail/"

        # https://www.esjzone.net/detail/{novel_id}.html
        self.chapter_api = "https://www.esjzone.net/detail/"

        # https://www.esjzone.net/forum/{novel_id}/{chapter_id}.html
        self.content_api = "https://www.esjzone.net/forum/"

        # https://www.esjzone.net/inc/mem_login.php
        self.login_api = "https://www.esjzone.net/inc/mem_login.php"

    @retry(stop_max_attempt_number=3, wait_random_min=200, wait_random_max=600)
    async def download_img(self, url, dir):
        async with aiohttp.ClientSession(headers=self.header) as session:
            async with session.get(url, cookies=self.cookie, proxy=self.proxy) as response:
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
    async def login(self):
        payload = "email=" + \
            urllib.parse.quote(self.email) + "&pwd=" + \
            urllib.parse.quote(self.password) + "&remember_me=on"
        login_header = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36',
                        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                        'Content-Length': str(len(payload)),
                        'Host': 'www.esjzone.net'}
        async with aiohttp.ClientSession(headers=login_header) as session:
            async with session.post(self.login_api, data=payload, proxy=self.proxy) as response:
                for i in session.cookie_jar:
                    self.cookie[i.key] = i.value

        return (await self.check_login())

    @retry(stop_max_attempt_number=3, wait_random_min=200, wait_random_max=600)
    async def check_login(self):
        async with aiohttp.ClientSession(headers=self.header) as session:
            async with session.get("https://www.esjzone.net/my/profile", cookies=self.cookie, proxy=self.proxy) as response:
                result = (await response.content.read()).decode('utf8')
                if (result.find("ESJ Zone") != -1):
                    return True

        return False

    @retry(stop_max_attempt_number=3, wait_random_min=200, wait_random_max=600)
    async def get_detail(self, novel_id):
        if ((await self.check_login()) == False):
            await self.login()
        async with aiohttp.ClientSession(headers=self.header) as session:
            async with session.get(self.detail_api + str(novel_id) + ".html", cookies=self.cookie, proxy=self.proxy) as response:
                result = zhconv.convert((await response.content.read()).decode('utf8'), 'zh-cn')
        parser = etree.HTMLParser(encoding='utf-8')
        html = etree.fromstring(result, parser=parser)
        description = []
        for i in html.xpath("/html/body/div[3]/section/div/div[1]/div[2]/div/div/div/p"):
            description.append(str(i.text))
            description.append('\n')
        detail = {}
        detail['name'] = str(html.xpath(
            "/html/body/div[3]/section/div/div[1]/div[1]/div[2]/h2")[0].text).replace(u'\u3000', u' ')
        detail['intro'] = "<br/>".join(description).replace(
            u'\u3000', u' ').replace('\r', '\n').replace('\n', '')
        detail['author'] = html.xpath(
            "/html/body/div[3]/section/div/div[1]/div[1]/div[2]/ul/li[2]/a")[0].text.replace(u'\u3000', u' ')
        detail['novel_id'] = int(novel_id)
        detail['cover'] = html.xpath(
            "/html/body/div[3]/section/div/div[1]/div[1]/div[1]/div[1]/a/img")[0].get('src')

        return detail

    @retry(stop_max_attempt_number=3, wait_random_min=200, wait_random_max=600)
    async def get_chapter(self, novel_id):
        if ((await self.check_login()) == False):
            await self.login()
        async with aiohttp.ClientSession(headers=self.header) as session:
            async with session.get(self.chapter_api + str(novel_id) + ".html", cookies=self.cookie, proxy=self.proxy) as response:
                result = zhconv.convert((await response.content.read()).decode('utf8'), 'zh-cn')
        parser = etree.HTMLParser(encoding='utf-8')
        html = etree.fromstring(result, parser=parser)
        temp = html.xpath(
            "//div[@id='chapterList']//p[@class='non'] | //div[@id='chapterList']//a[@target='_blank']")
        volume = [{'name': 'extra', 'volume_id': 0, 'chapter': []}]
        temp1 = {}
        vid = 1
        cid = 0
        for i in range(len(temp)):
            if (temp[i].tag == 'p' and (i+1) != len(temp) and temp[i+1].tag == 'a'):
                if (len(temp1) != 0):
                    volume.append(temp1)
                    temp1 = {}
                temp1['name'] = str(temp[i].text)
                temp1['volume_id'] = vid
                vid += 1
                temp1['chapter'] = []
            elif (temp[i].tag == 'a'):
                if ((temp[i].get('href')).find('esjzone') != -1):
                    try:
                        temp1['chapter'].append(
                            {"name": str(temp[i].get('data-title')), "chapter_id": int((urllib.parse.urlparse(temp[i].get('href')).path).split('/')[-1][:-5])})
                    except:
                        volume[0]['chapter'].append(
                            {"name": str(temp[i].get('data-title')), "chapter_id": int((urllib.parse.urlparse(temp[i].get('href')).path).split('/')[-1][:-5])})
                else:
                    try:
                        text = '<a href = "' + \
                            (temp[i].get('href')) + '"> ' + \
                            (temp[i].get('href')) + ' </a>'
                        temp1['chapter'].append(
                            {"name": str(temp[i].get('data-title')), "chapter_id": cid, "text": text})
                        cid += 1
                    except:
                        text = '<a href = "' + \
                            (temp[i].get('href')) + '"> ' + \
                            (temp[i].get('href')) + ' </a>'
                        volume[0]['chapter'].append(
                            {"name": str(temp[i].get('data-title')), "chapter_id": cid, "text": text})
                        cid += 1

        if (len(temp1) != 0):
            volume.append(temp1)

        if (len(volume[0]['chapter']) == 0):
            del(volume[0])

        return volume

    @retry(stop_max_attempt_number=3, wait_random_min=200, wait_random_max=600)
    async def get_content(self, novel_id, volume_id, chapter_id):
        if ((await self.check_login()) == False):
            await self.login()
        async with aiohttp.ClientSession(headers=self.header) as session:
            async with session.get(self.content_api + str(novel_id) + '/' + str(chapter_id) + ".html", cookies=self.cookie, proxy=self.proxy) as response:
                result = zhconv.convert((await response.content.read()).decode('utf8'), 'zh-cn').replace('壹', '一').replace('贰', '二').replace('叁', '三')
        soup = BeautifulSoup(result, features='lxml')
        content = soup.find_all(name='div', class_='forum-content mt-3')
        temp = soup.find_all(name='h2')[0].text
        temp = "<h2>" + temp + "</h2>"
        content = (html.unescape("<br/>".join(
            list(map(str, content[0].contents))))).replace('<p>', '').replace('</p>', '').replace('\r', '\n').replace('\n', '')
        while(content.find('<br>') != -1):
            content = content.replace('<br>', '<br/>')
        while(content.find('<br/><br/><br/>') != -1):
            content = content.replace('<br/><br/><br/>', '<br/><br/>')
        content = (temp + content).encode('utf8')
        soup = BeautifulSoup(content, features='lxml')
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
        if ((await self.check_login()) == False):
            await self.login()
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
                        if ("text" not in j.keys()):
                            content = await self.get_content(
                                info['novel_id'], i['volume_id'], j['chapter_id'])
                            content = self.localize_content(
                                content, chapter_dir)
                        else:
                            content = j['text'].encode('utf8')
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
                   'module': 'esjzone', 'state': 3})
        except Exception as e:
            print(e)
            try:
                await asyncio.wait(self.background_tasks)
            except:
                pass
            t.send({'action': 'finish', 'id': novel_id,
                   'module': 'esjzone', 'state': 1})
            return
