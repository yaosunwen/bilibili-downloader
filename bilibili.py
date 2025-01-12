import os
import json
import re
import traceback

import requests

import typer
from typing_extensions import Annotated

from tqdm import tqdm


ffmpeg_path = os.path.join(os.path.dirname(__file__), 'ffmpeg')
if os.path.exists(ffmpeg_path):
    os.environ['IMAGEIO_FFMPEG_EXE'] = ffmpeg_path
import moviepy


app = typer.Typer(no_args_is_help=True, help='download bilibili video and convert to mp3')


windows_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/42.0.2311.135 Safari/537.36 Edge/12.246'
# android_agent = 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36'
# iphone_agent = 'Mozilla/5.0 (iPhone14,3; U; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/602.1.50 (KHTML, like Gecko) Version/10.0 Mobile/19A346 Safari/602.1'


class BilibiliVideoHtml:
    def __init__(self, url, title=None, video_url=None, audio_url=None):
        self.url = url
        self.title = title
        self.video_url = video_url
        self.audio_url = audio_url
        self.loaded = False
    
    def load(self):
        if self.loaded:
            return
        
        self.loaded = True
        
        headers = {
            'referer': 'https://www.bilibili.com',
            'user-agent': windows_agent
        }
        html = requests.get(self.url, headers=headers).text

        initial_state_match = re.search('<script>window\.__INITIAL_STATE__=(.*?);\(function\(\).*</script>', html)
        if not initial_state_match:
            raise Exception('Could not find initial state, it should be assigned to window.__INITIAL_STATE__')
        # print(initial_state_match.group(1))
        initial_state = json.loads(initial_state_match.group(1))
        self.video_page_list = initial_state["videoData"]["pages"]

        play_information_match = re.search('<script>window\.__playinfo__=(.*?)</script>', html)
        if not play_information_match:
            raise Exception('Could not find play information, it should be assigned to window.__playinfo__')
        # print(play_information_match.group(1))
        play_information = json.loads(play_information_match.group(1))

        self.video_url = play_information["data"]["dash"]["video"][0]["base_url"]
        self.audio_url = play_information["data"]["dash"]["audio"][0]["base_url"]


class BilibiliVideoPage(BilibiliVideoHtml):
    def __init__(self, url, title):
        super().__init__(url, title=title)
    
    def get_video_url(self):
        self.load()
        return self.video_url
    
    def get_audio_url(self):
        self.load()
        return self.audio_url
    
    def get_video_title(self):
        return self.title


class BilibiliVideoListPage(BilibiliVideoHtml):
    def __init__(self, url):
        super().__init__(url)

        url_match = re.match('https?://www.bilibili.com/video/([^/]+)/?(\?.*)?', self.url)
        if not url_match:
            raise Exception(f'url format error : {self.url}')
        self.bvid = url_match.group(1)

    def get_page_list(self):
        self.load()
        items = self.video_page_list
        return [BilibiliVideoPage('https://www.bilibili.com/video/' + self.bvid + '?p=' + str(item['page']), item['part'])
                for item in items]


class BilibiliMediaDownloader:
    def __init__(self, media_url, output_path):
        self.media_url = media_url
        self.output_path = output_path
    
    def download(self):
        print('download', self.media_url, 'to', self.output_path)

        if os.path.exists(self.output_path):
            print(f'{self.output_path} exists, skipping to download')
            return
        
        dirname = os.path.dirname(self.output_path)
        basename = os.path.basename(self.output_path)
        temp_path = os.path.join(dirname, '__temp__' + basename)
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        
        headers = {
            'referer': 'https://www.bilibili.com/',
            'user-agent': windows_agent
        }
        response = requests.get(self.media_url, stream=True, headers=headers)
        content_length = int(response.headers.get('content-length',0))
        with open(temp_path, mode='wb') as file, tqdm(
                desc=basename,
                total=content_length,
                unit='iB',
                unit_scale=True,
                unit_divisor=1024
            ) as progress_bar:
                for chunk in response.iter_content(chunk_size=1024*8):
                    size = file.write(chunk)
                    progress_bar.update(size)
        
        os.rename(temp_path, self.output_path)


class BilibiliVideoConverter:
    def __init__(self, video_path, output_dir=None) -> None:
        self.video_path = video_path
        self.output_dir = output_dir
        if self.output_dir is None:
            self.output_dir = os.path.dirname(self.video_path)
    
    def convert_to_mp3(self):
        video_base_name = os.path.basename(self.video_path)
        mp3_base_name = os.path.splitext(video_base_name)[0] + '.mp3'
        mp3_temp_name = os.path.splitext(video_base_name)[0] + '.tmp.mp3'

        mp3_path = os.path.join(self.output_dir, mp3_base_name)
        print('convert', self.video_path, 'to', mp3_path)

        if os.path.exists(mp3_path):
            print(f'{mp3_path} exists')
            return
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        temp_path = os.path.join(self.output_dir, mp3_temp_name)
        if os.path.exists(temp_path):
            os.remove(temp_path)
    
        with moviepy.VideoFileClip(self.video_path) as c:
            c.audio.write_audiofile(temp_path)

        os.rename(temp_path, mp3_path)


class BilibiliAudioConverter:
    def __init__(self, audio_path, output_dir=None) -> None:
        self.audio_path = audio_path
        self.output_dir = output_dir
        if self.output_dir is None:
            self.output_dir = os.path.dirname(self.audio_path)
    
    def convert_to_mp3(self):
        audio_base_name = os.path.basename(self.audio_path)
        mp3_base_name = os.path.splitext(audio_base_name)[0] + '.mp3'
        mp3_temp_name = os.path.splitext(audio_base_name)[0] + '.tmp.mp3'

        mp3_path = os.path.join(self.output_dir, mp3_base_name)
        print('convert', self.audio_path, 'to', mp3_path)

        if os.path.exists(mp3_path):
            print(f'{mp3_path} exists')
            return
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        temp_path = os.path.join(self.output_dir, mp3_temp_name)
        if os.path.exists(temp_path):
            os.remove(temp_path)
    
        with moviepy.AudioFileClip(self.audio_path) as c:
            c.write_audiofile(temp_path)

        os.rename(temp_path, mp3_path)


@app.command()
def main(
    url: Annotated[str, typer.Option(prompt=True, help="bilibili url, as https://www.bilibili.com/video/{bvid}")],
    video_output_dir: Annotated[str, typer.Option()] = '.',
    audio_output_dir: Annotated[str, typer.Option()] = None
):
    video_page_list = BilibiliVideoListPage(url)
    for video_page in video_page_list.get_page_list():
        video_output_path = os.path.join(video_output_dir, video_page.get_video_title() + '.mp4')
        if os.path.exists(video_output_path):
            print(f'{video_output_path} exists')
        else:
            try:
                BilibiliMediaDownloader(video_page.get_audio_url(), video_output_path).download()
            except:
                traceback.print_exc()
        
        try:
            BilibiliAudioConverter(video_output_path, audio_output_dir).convert_to_mp3()
        except:
            traceback.print_exc()


if __name__ == '__main__':
    app()