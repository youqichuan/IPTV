import re
import requests
import logging
from collections import OrderedDict
from datetime import datetime
import config
import urllib.parse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler("function.log", "w", encoding="utf-8"), logging.StreamHandler()])

# 将demo.txt中的频道列表转换为list，结果如下
'''
template_channels = {
    "央视频道": ["CCTV1", "CCTV2"],
    "卫视频道": ["北京卫视","湖南卫视"]
}
'''
def parse_template(template_file):
    template_channels = OrderedDict()
    current_category = None

    with open(template_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "#genre#" in line:
                    current_category = line.split(",")[0].strip()
                    template_channels[current_category] = []
                elif current_category:
                    channel_name = line.split(",")[0].strip()
                    template_channels[current_category].append(channel_name)

    return template_channels

def change_cctv_channel(channel_name):   
    # 将频道名称全部转换为大写
    channel_name = channel_name.upper()
    
    # 定义正则表达式模式，央视频道中必定包含CCTV和至少1个数字，包含任意的-、空格和中文
    pattern = r"CCTV[-]*\d+[\s\u4e00-\u9fa5]*"
    
    # 检查字符串是否符合模式
    if re.search(pattern, channel_name):
        # 去除 "-"、空格和中文字符
        cleaned_channel_name = re.sub(r"[-\s\u4e00-\u9fa5]", "", channel_name)
        return cleaned_channel_name
    else:
        # 如果不符合模式，返回原始字符串
        return channel_name

# 去除 URL 中的 $LR 及后面的字符
def clean_url(url):
    result = re.sub(r'\$LR.*', '', url)
    
    # 移除 :80/，将:80/替换为/
    result = re.sub(r':80/', '/', result)
    if result.endswith("?"):
        result = result[:-1]
    return result

# 检查 URL 是否包含特殊符号
def is_valid_url(url):
    if "【" in url or "】" in url or "#http" in url:
        # logging.warning(f"URL contains invalid characters: {url}")
        return False
    return True

# 提取域名的函数
def extract_domain(url):
    parsed_url = urllib.parse.urlparse(url)
    return parsed_url.netloc  # 返回域名部分

# 解析IPTV源地址，并抓取频道信息，结果如下
'''
{
    "央视频道": [
        ("CCTV1", "http://cctv1.com"),
        ("CCTV2", "http://cctv2.com"),
        ("CCTV3", "http://cctv3.com")
    ],
    "卫视频道": [("北京卫视", "http://bjtv.com")]
}
'''
def fetch_channels(url):
    channels = OrderedDict()

    try:
        response = requests.get(url)
        response.raise_for_status()
        response.encoding = 'utf-8'
        lines = response.text.split("\n")
        current_category = None
        is_m3u = any("#EXTINF" in line for line in lines[:15])
        source_type = "m3u" if is_m3u else "txt"
        logging.info(f"url: {url} 获取成功，判断为{source_type}格式")

        if is_m3u:
            for line in lines:
                line = line.strip()
                if line.startswith("#EXTINF"):
                    match = re.search(r'group-title="(.*?)",(.*)', line)
                    if match:
                        current_category = match.group(1).strip()
                        channel_name = match.group(2).strip()
                        # 如果包含CCTV，则去除"-"、空格和中文字符。
                        channel_name = change_cctv_channel(channel_name)
                        if current_category not in channels:
                            channels[current_category] = []
                elif line and not line.startswith("#"):
                    channel_url = line.strip()
                    # 清理url地址，去掉最后的？
                    channel_url = clean_url(channel_url)
                    # 增加url的判断，如果带有【】或者#http的需要进行过滤
                    # 原始代码
                    # if current_category and channel_name:
                    if current_category and channel_name and is_valid_url(channel_url):
                        if (channel_name, channel_url) not in set(channels[current_category]):
                            channels[current_category].append((channel_name, channel_url))
        else:
            for line in lines:
                line = line.strip()
                if "#genre#" in line:
                    current_category = line.split(",")[0].strip()
                    channels[current_category] = []
                elif current_category:
                    match = re.match(r"^(.*?),(.*?)$", line)
                    if match:
                        channel_name = match.group(1).strip()
                        # 如果包含CCTV，则去除"-"、空格和中文字符。
                        channel_name = change_cctv_channel(channel_name)
                        channel_url = match.group(2).strip()
                         # 清理url地址，去掉最后的？
                        channel_url = clean_url(channel_url)
                        # 增加url的判断，如果带有【】或者#http的需要进行过滤
                        # 原始代码 
                        # channels[current_category].append((channel_name, channel_url))
                        if (channel_name, channel_url) not in set(channels[current_category]) and is_valid_url(channel_url):
                            channels[current_category].append((channel_name, channel_url))
                    elif line:
                        channels[current_category].append((line, ''))
        if channels:
            categories = ", ".join(channels.keys())
            logging.info(f"url: {url} 爬取成功✅，包含频道分类: {categories}")
    except requests.RequestException as e:
        logging.error(f"url: {url} 爬取失败❌, Error: {e}")

    return channels

def match_channels(template_channels, all_channels):
    matched_channels = OrderedDict()

    for category, channel_list in template_channels.items():
        matched_channels[category] = OrderedDict()
        for channel_name in channel_list:
            for online_category, online_channel_list in all_channels.items():
                for online_channel_name, online_channel_url in online_channel_list:
                    if channel_name == online_channel_name:
                        matched_channels[category].setdefault(channel_name, []).append(online_channel_url)

    return matched_channels

def filter_source_urls(template_file):
    # demo.txt中的频道列表转换为list
    template_channels = parse_template(template_file)
    # 读取配置中要抓取的IPTV源地址
    source_urls = config.source_urls

    all_channels = OrderedDict()
    # 遍历IPTV源地址进行解析
    for url in source_urls:
        # 解析IPTV源地址，并抓取频道信息
        fetched_channels = fetch_channels(url)
        for category, channel_list in fetched_channels.items():
            if category in all_channels:
                all_channels[category].extend(channel_list)
            else:
                all_channels[category] = channel_list

    matched_channels = match_channels(template_channels, all_channels)

    return matched_channels, template_channels

def is_ipv6(url):
    return re.match(r'^http:\/\/\[[0-9a-fA-F:]+\]', url) is not None

def updateChannelUrlsM3U(channels, template_channels):
    written_urls = set()

    current_date = datetime.now().strftime("%Y-%m-%d")
    for group in config.announcements:
        for announcement in group['entries']:
            if announcement['name'] is None:
                announcement['name'] = current_date

    with open("live.m3u", "w", encoding="utf-8") as f_m3u:
        f_m3u.write(f"""#EXTM3U x-tvg-url={",".join(f'"{epg_url}"' for epg_url in config.epg_urls)}\n""")

        with open("live.txt", "w", encoding="utf-8") as f_txt:
            for group in config.announcements:
                pass
                # f_txt.write(f"{group['channel']},#genre#\n")
                for announcement in group['entries']:
                    pass
                    # f_m3u.write(f"""#EXTINF:-1 tvg-id="1" tvg-name="{announcement['name']}" tvg-logo="{announcement['logo']}" group-title="{group['channel']}",{announcement['name']}\n""")
                    # f_m3u.write(f"{announcement['url']}\n")
                    # f_txt.write(f"{announcement['name']},{announcement['url']}\n")
            # 遍历频道模板
            for category, channel_list in template_channels.items():
                f_txt.write(f"{category},#genre#\n")
                # 如果模板中的频道分组在抓取到的频道分组中
                if category in channels:
                    # 遍历模板中的频道列表
                    for channel_name in channel_list:
                        # 如果模板中的频道列表在抓取到的频道列表
                        if channel_name in channels[category]:
                            # 对则对该频道的所有数据进行排序
                            # 原始排序
                            # sorted_urls = sorted(channels[category][channel_name], key=lambda url: not is_ipv6(url) if config.ip_version_priority == "ipv6" else is_ipv6(url))
                            
                            # 代码修改根据 IPv6/IPv4 优先级、域名和完整 URL 排序
                            sorted_urls = sorted(
                                channels[category][channel_name],
                                key=lambda url: (
                                    not is_ipv6(url) if config.ip_version_priority == "ipv6" else is_ipv6(url),  # IPv6/IPv4 优先级
                                    extract_domain(url),  # 域名排序
                                    url  # 完整 URL 排序
                                )
                            ) 
                            
                            filtered_urls = []
                            for url in sorted_urls:
                                if url and url not in written_urls and not any(blacklist in url for blacklist in config.url_blacklist):
                                    filtered_urls.append(url)
                                    written_urls.add(url)

                            total_urls = len(filtered_urls)
                            for index, url in enumerate(filtered_urls, start=1):
                                if is_ipv6(url):
                                    url_suffix = f"$LR•IPV6" if total_urls == 1 else f"$LR•IPV6『线路{index}』"
                                else:
                                    url_suffix = f"$LR•IPV4" if total_urls == 1 else f"$LR•IPV4『线路{index}』"
                                if '$' in url:
                                    base_url = url.split('$', 1)[0]
                                else:
                                    base_url = url

                                # 原始代码，增加后缀
                                # new_url = f"{base_url}{url_suffix}"
                                # 修改代码，取消后缀
                                new_url = f"{base_url}"

                                f_m3u.write(f"#EXTINF:-1 tvg-id=\"{index}\" tvg-name=\"{channel_name}\" tvg-logo=\"https://gcore.jsdelivr.net/gh/yuanzl77/TVlogo@master/png/{channel_name}.png\" group-title=\"{category}\",{channel_name}\n")
                                f_m3u.write(new_url + "\n")
                                f_txt.write(f"{channel_name},{new_url}\n")

            f_txt.write("\n")

if __name__ == "__main__":
    template_file = "demo.txt"
    channels, template_channels = filter_source_urls(template_file)
    updateChannelUrlsM3U(channels, template_channels)
