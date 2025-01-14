import re
import time
import httpx
import jinja2
from pathlib import Path
from bs4 import BeautifulSoup, Tag
from typing import List, Tuple, Union

from utils.migang.http import html_to_pic
from configs.config import Config

tpl_path = Path(__file__).parent / "templates"
env = jinja2.Environment(loader=jinja2.FileSystemLoader(tpl_path), enable_async=True)


def retry(func):
    async def wrapper(*args, **kwargs):
        for i in range(3):
            try:
                return await func(*args, **kwargs)
            except:
                continue
        raise

    return wrapper


headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36"
}

if Config.get_config("zhenxun_plugin_shindan", "SHINDANMAKER_COOKIE"):
    headers["cookie"] = Config.get_config("zhenxun_plugin_shindan", "SHINDANMAKER_COOKIE")


@retry
async def get(client: httpx.AsyncClient, url: str, **kwargs):
    return await client.get(url, headers=headers, timeout=20, **kwargs)


@retry
async def post(client: httpx.AsyncClient, url: str, **kwargs):
    return await client.post(url, headers=headers, timeout=20, **kwargs)


async def get_shindan_title(id: str) -> str:
    url = f"https://shindanmaker.com/{id}"
    async with httpx.AsyncClient() as client:
        resp = await get(client, url)
        if resp.status_code == 302:
            resp = await get(client, resp.headers["location"])
        dom = BeautifulSoup(resp.text, "lxml")
        title = dom.find("h1", {"id": "shindanTitle"})
        assert title
        return title.text


async def make_shindan(id: str, name: str, mode="image") -> Union[str, bytes]:
    url = f"https://shindanmaker.com/{id}"
    seed = time.strftime("%y%m%d", time.localtime())
    async with httpx.AsyncClient() as client:
        resp = await get(client, url)
        if resp.status_code == 302:
            resp = await get(client, resp.headers["location"])
        dom = BeautifulSoup(resp.text, "lxml")
        token = dom.find("form", {"id": "shindanForm"}).find("input")["value"]  # type: ignore
        payload = {"_token": token, "shindanName": name + seed, "hiddenName": "名無しのR"}
        resp = await post(client, url, json=payload)

    content = resp.text
    if mode == "image":
        html, has_chart = await render_html(content)
        html = html.replace(seed, "")
        return await html_to_pic(
            html,
            template_path=f"file://{tpl_path.absolute()}",
            wait=2000 if has_chart else 0,
            viewport={"width": 750, "height": 100},
        )
    else:
        dom = BeautifulSoup(content, "lxml")
        result = dom.find("span", {"id": "shindanResult"})
        assert isinstance(result, Tag)
        for img in result.find_all("img"):
            img.replace_with(img["src"])
        return result.text.replace(seed, "")


async def render_html(content: str) -> Tuple[str, bool]:
    dom = BeautifulSoup(content, "lxml")
    result_js = str(dom.find("script", string=re.compile(r"saveResult")))
    title = str(dom.find("h1", {"id": "shindanResultAbove"}))
    result = str(dom.find("div", {"id": "shindanResultBlock"}))
    has_chart = "chart.js" in content

    shindan_tpl = env.get_template("shindan.html")
    html = await shindan_tpl.render_async(
        result_js=result_js, title=title, result=result, has_chart=has_chart
    )
    return html, has_chart


async def render_shindan_list(sd_list: List[dict]) -> bytes:
    tpl = env.get_template("shindan_list.html")
    html = await tpl.render_async(shindan_list=sd_list)
    return await html_to_pic(
        html,
        template_path=f"file://{tpl_path.absolute()}",
        viewport={"width": 100, "height": 100},
    )
