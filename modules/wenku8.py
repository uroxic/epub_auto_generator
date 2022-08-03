import asyncio
import json
import os
import re
from multiprocessing import Pipe

import aiofiles
import aiohttp
from bs4 import BeautifulSoup
from lxml import etree
from retrying import retry


class fetcher(object):
    def __init__(self, proxy=None):
        self.save_dir = "./wenku8/web"
        self.proxy = proxy
        self.header = [('User-Agent',
                        'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1941.0 Safari/537.36')]
        self.background_tasks = set()

        # https://www.wenku8.net/book/{novel_id}.htm
        self.detail_api = "https://www.wenku8.net/book/"

        # https://www.wenku8.net/novel/{novel_id // 1000}/{novel_id}/index.htm
        self.chapter_api = "https://www.wenku8.net/novel/"

        # https://www.wenku8.net/novel/{novel_id // 1000}/{novel_id}/{chapter_id}.htm
        self.content_api = "https://www.wenku8.net/novel/"

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
        async with aiohttp.ClientSession(headers=self.header) as session:
            async with session.get(self.detail_api + str(novel_id) + ".htm", proxy=self.proxy) as response:
                result = (await response.content.read()).decode('gbk')
        parser = etree.HTMLParser(encoding='utf-8')
        html = etree.fromstring(result, parser=parser)
        detail = {}
        detail['name'] = html.xpath(
            "/html/body/div[5]/div/div/div[1]/table[1]/tr[1]/td/table/tr/td[1]/span/b")[0].text
        detail['intro'] = "".join(html.xpath(
            "/html/body/div[5]/div/div/div[1]/table[2]/tr/td[2]/span[6]/text()")).replace(u'\u3000', u' ').replace('\r', '\n')
        detail['author'] = html.xpath(
            "/html/body/div[5]/div/div/div[1]/table[1]/tr[2]/td[2]")[0].text[5:]
        detail['novel_id'] = int(novel_id)
        detail['cover'] = html.xpath(
            "/html/body/div[5]/div/div/div[1]/table[2]/tr/td[1]/img")[0].get('src')

        return detail

    @retry(stop_max_attempt_number=3, wait_random_min=200, wait_random_max=600)
    async def get_chapter(self, novel_id):
        async with aiohttp.ClientSession(headers=self.header) as session:
            async with session.get(self.chapter_api + str(int(novel_id) // 1000) + '/' + str(novel_id) + "/index.htm", proxy=self.proxy) as response:
                result = (await response.content.read()).decode('gbk')
        parser = etree.HTMLParser(encoding='utf-8')
        html = etree.fromstring(result, parser=parser)
        temp = html.xpath("//td[@class='vcss'] | //td[@class='ccss']/node()")
        while(1):
            try:
                temp.remove('\xa0')
            except Exception as e:
                print(e)
                break
        volume = []
        temp1 = {}
        for i in temp:
            if (i.get('class') == 'vcss'):
                if (len(temp1) != 0):
                    volume.append(temp1)
                    temp1 = {}
                temp1['name'] = i.text
                temp1['volume_id'] = i.get('vid')
                temp1['chapter'] = []
            else:
                temp1['chapter'].append(
                    {"name": i.text, "chapter_id": int(i.get('href')[:-4])})
        if (len(temp1) != 0):
            volume.append(temp1)

        return volume

    @retry(stop_max_attempt_number=3, wait_random_min=200, wait_random_max=600)
    async def get_content(self, novel_id, volume_id, chapter_id):
        async with aiohttp.ClientSession(headers=self.header) as session:
            async with session.get(self.content_api + str(int(novel_id) // 1000) + '/' + str(novel_id) + '/' + str(chapter_id) + ".htm", proxy=self.proxy) as response:
                result = (await response.content.read()).decode('gbk')
        soup = BeautifulSoup(result, features='lxml')
        content = soup.find_all(name='div', id='content')
        temp = soup.find_all(name='div', id='title')[0].text
        content = "".join(
            list(map(str, content[0].contents[2:-2]))).replace('\r', '\n').replace('\n', '')
        content = (temp + '<br/><br/>' + content).encode('utf8')
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
        imgs = soup.find_all(name='div', class_='divimage')
        if(len(imgs) != 0):
            for i in imgs:
                i.replace_with(i.contents[0].contents[0])
        imgs = soup.find_all('img')
        if(len(imgs) != 0):
            for i in imgs:
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
                volume_dir = novel_dir + '/' + self.correct_dir(i['name'])
                self.check_dir(volume_dir)
                for j in i['chapter']:
                    chapter_dir = volume_dir + '/' + \
                        self.correct_dir(j['name'])
                    self.check_dir(chapter_dir)
                    if((lazy == False) or (os.path.exists(chapter_dir + '/' + 'text.htm') == False)):
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
            except Exception as e:
                print(e)
                pass
            t.send({'action': 'finish', 'id': novel_id,
                   'module': 'wenku8', 'state': 3})
        except Exception as e:
            print(e)
            t.send({'action': 'finish', 'id': novel_id,
                   'module': 'wenku8', 'state': 1})
            return
        return