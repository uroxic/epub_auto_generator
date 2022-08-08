import asyncio
import json
import os
import re
from multiprocessing import Pipe

from bs4 import BeautifulSoup
from ebooklib import epub


def correct_dir(dir):
    return (re.sub('([^\u0030-\u0039\u0041-\u007a\u4e00-\u9fa5])', '', dir.strip()))[:31]


def make_epub(module, novel_id, t):
    novel_list = {}
    try:
        jsondir = "./" + module + "/novel.json"
        with open(jsondir, 'rb') as f:
            novel_list = (f.read()).decode('utf8')
        novel_list = json.loads(novel_list)
        novel_name = novel_list[novel_id]["name"]
        book_dir = './' + module + "/web/" + correct_dir(novel_name)
        save_dir = './' + module + "/epub"

        if (os.path.exists(save_dir) == False):
            os.makedirs(save_dir)

        with open(book_dir + '/' + 'info.json', 'rb') as f:
            info = f.read().decode('utf8')
        with open(book_dir + '/' + 'volume.json', 'rb') as f:
            volume = f.read().decode('utf8')

        info = json.loads(info)
        volume = json.loads(volume)

        book = epub.EpubBook()

        # add metadata
        book.set_identifier(info['name'])
        book.set_title(info['name'])
        book.set_language('zh-cn')
        book.add_author(info['author'])
        book.set_cover("cover.jpg", open(
            book_dir + '/' + 'cover.jpg', 'rb').read())

        # intro chapter
        c0 = epub.EpubHtml(title=info['name'], file_name='intro.xhtml')
        c0.content = '<html><head></head><body><img src="img/cover.jpg"/><h1>' + \
            info['name'] + '</h1><p>' + info['intro'] + '</p></body></html>'
        cover = epub.EpubItem(uid='main-cover', file_name="img/cover.jpg", media_type='image/jpg', content=open(
            book_dir + '/' + 'cover.jpg', 'rb').read())

        # add chapters to the book
        book.add_item(c0)
        book.add_item(cover)

        # create spine
        book.spine = [c0, 'nav']

        # create table of contents
        # - add section
        # - add auto created links to chapters

        book.toc = [c0, 'nav']  # epub.Section('title')
        count = 0
        img_id = 0

        for i in volume:
            temp = []
            href_link = str(count+1)+'.xhtml'
            for j in i['chapter']:
                count += 1
                c = epub.EpubHtml(
                    title=j['name'], file_name=str(count)+'.xhtml')
                text = open(book_dir + '/' + correct_dir(i['name']) + '/' + correct_dir(j['name']) +
                            '/' + 'text.htm', 'rb').read().decode('utf8')

                soup = BeautifulSoup(text, features='lxml')
                imgs = soup.find_all('img')
                if(len(imgs) != 0):
                    for k in imgs:
                        try:
                            suffix = '.' + (str(k['src']).split('.'))[-1]
                            img_name = 'img' + str(img_id)
                            img_cont = open(
                                book_dir + '/' + correct_dir(i['name']) + '/' + correct_dir(j['name']) + '/' + str(k['src']), 'rb').read()
                            eimg = epub.EpubItem(
                                uid=img_name, file_name=(img_name + suffix), media_type='image/jpg', content=img_cont)
                            book.add_item(eimg)
                            k['src'] = (img_name + suffix)
                            img_id += 1
                        except Exception as e:
                            print(e)
                            pass

                c.content = soup.prettify()
                book.add_item(c)

                temp.append(c)
                book.spine.append(c)
            book.toc.append([epub.Section(i['name'], href=href_link), temp])

        # add navigation files
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # create epub file
        epub.write_epub(save_dir + '/' +
                        correct_dir(info['name']) + '.epub', book, {})
        t.send({'action': 'finish', 'id': novel_id, 'module': module, 'state': 5})
    except Exception as e:
        print(e)
        t.send({'action': 'finish', 'id': novel_id, 'module': module, 'state': 3})
        return
    return
