import asyncio
import base64
import hashlib
import html
import json
import os
import re
import time
from multiprocessing import Pipe

import aiofiles
import aiohttp
import zhconv
from bs4 import BeautifulSoup
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA
from google.protobuf import json_format
from retrying import retry

import modules.NovelChapterResponse_pb2 as NovelChapterResponse_pb2
import modules.NovelDetailResponse_pb2 as NovelDetailResponse_pb2


class fetcher(object):
    def __init__(self, proxy=None):
        self.save_dir = "./dmzj/web"
        self.proxy = proxy
        self.header = [('User-Agent',
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36')]
        self.background_tasks = set()

        # https://nnv4api.muwai.com/novel/detail/{novel_id}
        self.detail_api = "https://nnv4api.muwai.com/novel/detail/"

        # https://nnv4api.muwai.com/novel/chapter/{novel_id}
        self.chapter_api = "https://nnv4api.muwai.com/novel/chapter/"

        # http://jurisdiction.muwai.com/lnovel/{volume_id}_{chapter_id}.txt
        self.content_api = "http://jurisdiction.muwai.com"

        self.PRIVATE_KEY = '-----BEGIN RSA PRIVATE KEY-----\n' + "MIICeAIBADANBgkqhkiG9w0BAQEFAASCAmIwggJeAgEAAoGBAK8nNR1lTnIfIes6oRWJNj3mB6OssDGx0uGMpgpbVCpf6+VwnuI2stmhZNoQcM417Iz7WqlPzbUmu9R4dEKmLGEEqOhOdVaeh9Xk2IPPjqIu5TbkLZRxkY3dJM1htbz57d/roesJLkZXqssfG5EJauNc+RcABTfLb4IiFjSMlTsnAgMBAAECgYEAiz/pi2hKOJKlvcTL4jpHJGjn8+lL3wZX+LeAHkXDoTjHa47g0knYYQteCbv+YwMeAGupBWiLy5RyyhXFoGNKbbnvftMYK56hH+iqxjtDLnjSDKWnhcB7089sNKaEM9Ilil6uxWMrMMBH9v2PLdYsqMBHqPutKu/SigeGPeiB7VECQQDizVlNv67go99QAIv2n/ga4e0wLizVuaNBXE88AdOnaZ0LOTeniVEqvPtgUk63zbjl0P/pzQzyjitwe6HoCAIpAkEAxbOtnCm1uKEp5HsNaXEJTwE7WQf7PrLD4+BpGtNKkgja6f6F4ld4QZ2TQ6qvsCizSGJrjOpNdjVGJ7bgYMcczwJBALvJWPLmDi7ToFfGTB0EsNHZVKE66kZ/8Stx+ezueke4S556XplqOflQBjbnj2PigwBN/0afT+QZUOBOjWzoDJkCQClzo+oDQMvGVs9GEajS/32mJ3hiWQZrWvEzgzYRqSf3XVcEe7PaXSd8z3y3lACeeACsShqQoc8wGlaHXIJOHTcCQQCZw5127ZGs8ZDTSrogrH73Kw/HvX55wGAeirKYcv28eauveCG7iyFR0PFB/P/EDZnyb+ifvyEFlucPUI0+Y87F" + '\n-----END RSA PRIVATE KEY-----'
        self.CONTENT_KEY = "IBAAKCAQEAsUAdKtXNt8cdrcTXLsaFKj9bSK1nEOAROGn2KJXlEVekcPssKUxSN8dsfba51kmHM"

    def rsa_decrypt(self, data: bytes, private_key):
        # 私钥解密
        pri_key = RSA.importKey(private_key)
        cipher = PKCS1_v1_5.new(pri_key)
        temp = base64.b64decode(data)
        back_text = b''
        for i in range(len(temp)//128):
            back_text += cipher.decrypt(temp[i*128: (i+1)*128], 0)
        return back_text

    def pb_to_json(self, pbStringRequest):
        # 将pbstring转化为jsonStringResponse返回
        jsonStringRequest = json_format.MessageToJson(pbStringRequest)
        return jsonStringRequest

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
            async with session.get(self.detail_api + str(novel_id), proxy=self.proxy) as response:
                result = await response.content.read()
        detail = NovelDetailResponse_pb2.NovelDetailResponse()
        data = self.rsa_decrypt(result, self.PRIVATE_KEY)
        detail.ParseFromString(data)
        detail = self.pb_to_json(detail)
        temp = (json.loads(detail))['Data']
        detail = {}
        detail['name'] = temp['Name']
        detail['intro'] = temp['Introduction']
        detail['author'] = temp['Authors']
        detail['novel_id'] = temp['NovelId']
        detail['cover'] = temp['Cover']

        return detail

    @retry(stop_max_attempt_number=3, wait_random_min=200, wait_random_max=600)
    async def get_chapter(self, novel_id):
        async with aiohttp.ClientSession(headers=self.header) as session:
            async with session.get(self.chapter_api + str(novel_id), proxy=self.proxy) as response:
                result = await response.content.read()
        chapter = NovelChapterResponse_pb2.NovelChapterResponse()
        data = self.rsa_decrypt(result, self.PRIVATE_KEY)
        chapter.ParseFromString(data)
        chapter = self.pb_to_json(chapter)
        temp = (json.loads(chapter))['Data']
        chapter = []
        for i in temp:
            temp0 = {}
            temp0['name'] = i['VolumeName']
            temp0['volume_id'] = i['VolumeId']
            temp0['chapter'] = []
            for j in i['Chapters']:
                temp1 = {}
                temp1['name'] = j['ChapterName']
                temp1['chapter_id'] = j['ChapterId']
                temp0['chapter'].append(temp1)
            chapter.append(temp0)

        return chapter

    @retry(stop_max_attempt_number=3, wait_random_min=200, wait_random_max=600)
    async def get_content(self, novel_id, volume_id, chapter_id):
        path = "/lnovel/" + str(volume_id) + "_" + str(chapter_id) + ".txt"
        ts = str(int(time.time()))

        curr_key = self.CONTENT_KEY + path
        curr_key += ts

        curr_key = hashlib.md5(curr_key.encode(
            encoding='UTF-8')).hexdigest()

        url = self.content_api + path + "?t=" + ts + "&k=" + curr_key

        async with aiohttp.ClientSession(headers=self.header) as session:
            async with session.get(url, proxy=self.proxy) as response:
                content = zhconv.convert((await response.content.read()).decode('utf8'), 'zh-cn').replace('壹', '一').replace('贰', '二').replace('叁', '三')
        content = (html.unescape(content)).replace(
            '\r', '\n').replace('\n', '')
        while(content.find('<br>') != -1):
            content = content.replace('<br>', '<br/>')
        while(content.find('<br/><br/><br/>') != -1):
            content = content.replace('<br/><br/><br/>', '<br/><br/>')
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
                   'module': 'dmzj', 'state': 3})
        except Exception as e:
            print(e)
            t.send({'action': 'finish', 'id': novel_id,
                   'module': 'dmzj', 'state': 1})
            return
        return
