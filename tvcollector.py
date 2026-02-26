#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IPTV直播源收集工具 - 最终优化版
优化测试效率和稳定性
"""

import requests
import re
import time
import os
import concurrent.futures
import warnings
import urllib3
from collections import defaultdict

# 禁用SSL警告
warnings.filterwarnings('ignore')
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class FinalIPTV:
    def __init__(self):
        # 源网址
        self.source_urls = [
      #      "https://gitee.com/mytv-android/iptv-api/raw/master/output/result.txt",
      #      "https://raw.githubusercontent.com/kimwang1978/collect-txt/refs/heads/main/others_output.txt",
            "https://gh-proxy.com/raw.githubusercontent.com/suxuang/myIPTV/main/ipv4.m3u",
        ]
        
        # 分类规则
        self.category_rules = {
            "央视": [r"CCTV[-_\d]+", r"央视", r"中央台"],
            "卫视": [r"卫视"],
            "地方台": [r"台$", r"电视台$"],
            "电影电视剧": [r"电影", r"剧场", r"电视剧", r"影院", r"影视"],
            "体育": [r"体育", r"足球", r"篮球", r"赛事", r"CCTV5"],
            "少儿动画": [r"少儿", r"动画", r"卡通", r"动漫", r"儿童"],
            "其他": []
        }
        
        # 测试设置 - 优化参数
        self.connect_timeout = 2  # 连接超时
        self.read_timeout = 3    # 读取超时
        self.max_workers = 10    # 减少并发数，避免过多超时
        
        # 要排除的源地址（单节目回放等）
        self.excluded_urls = [
            "https://p2.bdstatic.com"
        ]
    
    def fetch_content(self, url):
        """获取网页内容"""
        try:
            print(f"正在获取: {url}")
            response = requests.get(url, timeout=10, verify=False)
            response.encoding = 'utf-8'
            return response.text
        except Exception as e:
            print(f"  获取失败: {e}")
            return None
    
    def extract_urls_from_line(self, url_part):
        """从一行中提取所有URL"""
        urls = []
        
        # 处理$分隔的多个源
        if '$' in url_part:
            parts = url_part.split('$')
            for part in parts:
                # 在每个部分中查找URL
                url_matches = re.findall(r'https?://[^\s$,;]*', part)
                for url in url_matches:
                    url = url.rstrip(' ,;')
                    if url and len(url) < 500:
                        # 检查是否是要排除的URL
                        if any(excluded_url in url for excluded_url in self.excluded_urls):
                            continue
                        urls.append(url)
        else:
            # 没有$符号，直接查找URL
            url_matches = re.findall(r'https?://[^\s,]*', url_part)
            for url in url_matches:
                url = url.rstrip(' ,;')
                if url and len(url) < 500:
                    # 检查是否是要排除的URL
                    if any(excluded_url in url for excluded_url in self.excluded_urls):
                        continue
                    urls.append(url)
        
        return urls
    
    def parse_line(self, line):
        """解析单行内容"""
        line = line.strip()
        if not line or line.startswith('#') or '#genre#' in line:
            return []
        
        # 跳过时间戳行（如：2026-02-02 01:04:08,http://...）
        if re.match(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', line):
            return []
        
        channels = []
        
        # 查找第一个逗号
        if ',' in line:
            try:
                # 分割频道名称和URL部分
                first_comma = line.find(',')
                channel_name = line[:first_comma].strip()
                url_part = line[first_comma+1:].strip()
                
                # 清理频道名
                channel_name = re.sub(r'[<>:"/\\|?*]', '', channel_name)
                
                # 跳过明显无效的（如纯时间戳或纯数字）
                if not channel_name or re.match(r'^\d+$', channel_name):
                    return []
                
                # 从URL部分提取所有URL
                urls = self.extract_urls_from_line(url_part)
                
                if not urls:
                    return []
                
                # 为每个URL创建一个频道条目
                for url in urls:
                    if len(url) > 500:
                        continue
                    
                    channels.append({
                        "name": channel_name,
                        "url": url
                    })
                
            except Exception:
                return []
        
        return channels
    
    def parse_m3u(self, content):
        """解析M3U格式的内容，返回频道列表"""
        channels = []
        lines = content.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith('#EXTINF:'):
                # 提取频道名称（优先使用tvg-name）
                tvg_name_match = re.search(r'tvg-name="([^"]+)"', line)
                if tvg_name_match:
                    channel_name = tvg_name_match.group(1).strip()
                else:
                    # 如果没有tvg-name，取逗号后的显示名称
                    comma_pos = line.rfind(',')
                    if comma_pos != -1:
                        channel_name = line[comma_pos+1:].strip()
                    else:
                        channel_name = "未知"
            
                # 清理非法字符
                channel_name = re.sub(r'[<>:"/\\|?*]', '', channel_name)
                if not channel_name:  # 跳过空名称
                    i += 1
                    continue

                # 寻找下一行作为URL（跳过空行和注释行）
                i += 1
                while i < len(lines):
                    url_line = lines[i].strip()
                    if url_line and not url_line.startswith('#'):
                        # 提取该行中的所有URL
                        urls = self.extract_urls_from_line(url_line)
                        for url in urls:
                            if len(url) > 500:
                                continue
                            # 排除特定URL
                            if any(excluded in url for excluded in self.excluded_urls):
                                continue
                            channels.append({
                                "name": channel_name,
                                "url": url
                            })
                        break
                    elif url_line.startswith('#EXTINF:'):
                        # 如果下一行又是EXTINF，说明没有URL，回退让外层处理
                        i -= 1
                        break
                    else:
                        i += 1  # 跳过空行或无关注释
            else:
                i += 1
        return channels

    def test_single_link(self, channel):
        """测试单个链接是否有效"""
        url = channel['url']
        
        try:
            # 设置请求头
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': '*/*',
                'Connection': 'close',
            }
            
            # 方法1: 尝试HEAD请求
            try:
                response = requests.head(
                    url, 
                    headers=headers, 
                    timeout=(self.connect_timeout, self.read_timeout), 
                    allow_redirects=True,
                    verify=False
                )
                
                if response.status_code in [200, 206, 301, 302]:
                    content_type = response.headers.get('Content-Type', '')
                    if any(x in content_type.lower() for x in ['video', 'audio', 'application', 'mpegurl']):
                        return channel, True
                    elif not content_type or content_type == 'application/octet-stream':
                        return channel, True
                    elif response.status_code in [301, 302]:
                        # 重定向，可能是有效的
                        return channel, True
            except:
                pass
            
            # 方法2: 尝试GET请求
            try:
                response = requests.get(
                    url,
                    headers=headers,
                    timeout=(self.connect_timeout, self.read_timeout),
                    stream=True,
                    verify=False
                )
                
                if response.status_code in [200, 206]:
                    # 快速检查是否是m3u文件
                    try:
                        # 只读取前100个字节
                        content_start = response.raw.read(100)
                        if b'#EXTM3U' in content_start:
                            return channel, True
                    except:
                        pass
                    
                    # 检查内容类型
                    content_type = response.headers.get('Content-Type', '')
                    if any(x in content_type.lower() for x in ['video', 'audio', 'application', 'mpegurl']):
                        return channel, True
            except:
                pass
            
            return channel, False
            
        except Exception:
            return channel, False
    
    def test_links(self, channels):
        """批量测试链接有效性"""
        if not channels:
            return []
        
        print(f"\n开始测试 {len(channels)} 个链接的有效性...")
        print("=" * 60)
        
        valid_channels = []
        total = len(channels)
        
        # 进度显示函数
        def update_progress(current, total, valid):
            percent = (current / total) * 100
            bar_length = 30
            filled_length = int(bar_length * current // total)
            bar = '█' * filled_length + '░' * (bar_length - filled_length)
            print(f"\r测试进度: [{bar}] {percent:.1f}% | 已测: {current}/{total} | 有效: {valid}", end='')
        
        # 使用线程池并发测试
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for channel in channels:
                futures.append(executor.submit(self.test_single_link, channel))
            
            completed = 0
            valid = 0
            
            # 设置总超时时间，避免长时间卡住
            timeout_seconds = max(30, len(channels) * 2)  # 至少30秒，最多每个链接2秒
            
            try:
                for future in concurrent.futures.as_completed(futures, timeout=timeout_seconds):
                    completed += 1
                    try:
                        channel, is_valid = future.result(timeout=1)
                        if is_valid:
                            valid += 1
                            valid_channels.append(channel)
                    except:
                        pass
                    
                    # 每测试10个更新一次进度
                    if completed % 10 == 0:
                        update_progress(completed, total, valid)
                        
            except concurrent.futures.TimeoutError:
                print(f"\n警告：测试超时，已完成 {completed}/{total} 个链接")
            except Exception as e:
                print(f"\n测试过程中出现错误: {e}")
        
        # 最终更新进度
        update_progress(completed, total, valid)
        
        print(f"\n\n测试完成！")
        print(f"总计: {total} 个链接")
        print(f"完成测试: {completed} 个")
        print(f"有效链接: {valid} 个")
        
        return valid_channels
    
    def categorize(self, channel_name):
        """分类"""
        for category, patterns in self.category_rules.items():
            if category == "其他":
                continue
            for pattern in patterns:
                if re.search(pattern, channel_name, re.IGNORECASE):
                    return category
        return "其他"
    
    def save_m3u(self, categorized, filename="IPTV.m3u"):
        """保存为M3U文件"""
        print(f"\n正在保存到: {filename}")
        
        # 按频道名分组，同一频道多个源相邻排列
        categorized_by_name = defaultdict(lambda: defaultdict(list))
        for category, channels in categorized.items():
            for channel in channels:
                categorized_by_name[category][channel['name']].append(channel)
        
        total_channels = 0
        total_sources = 0
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            f.write(f'# 生成时间: {time.strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write(f'# 版本: 最终优化版\n\n')
            
            # 按分类顺序写入
            categories_order = ["央视", "卫视", "地方台", "电影电视剧", "体育", "少儿动画", "其他"]
            
            for category in categories_order:
                if category in categorized_by_name:
                    channels_dict = categorized_by_name[category]
                    if not channels_dict:
                        continue
                    
                    f.write(f'\n# genre: {category}\n')
                    
                    # 对频道进行排序
                    sorted_channels = self.sort_channels(list(channels_dict.keys()), category)
                    
                    for channel_name in sorted_channels:
                        sources = channels_dict[channel_name]
                        total_channels += 1
                        
                        for source in sources:
                            total_sources += 1
                            # 修改1: 不添加编号，直接使用分类名称
                            f.write(f'#EXTINF:-1 tvg-name="{channel_name}" group-title="{category}",{channel_name}\n')
                            f.write(f'{source["url"]}\n')
        
        # 显示统计信息
        print(f"已保存 {total_channels} 个频道，{total_sources} 个源")
        
        # 显示文件信息
        if os.path.exists(filename):
            file_size = os.path.getsize(filename)
            print(f"文件大小: {file_size} 字节 ({file_size/1024:.1f} KB)")
        
        return total_channels, total_sources
    
    def sort_channels(self, channel_list, category):
        """对频道进行排序"""
        if category == "央视":
            # 对央视频道进行特殊排序
            return sorted(channel_list, key=self.cctv_sort_key)
        else:
            # 其他频道按字母顺序排序
            return sorted(channel_list)
    
    def cctv_sort_key(self, channel_name):
        """为央视频道生成排序键值"""
        # 查找CCTV后的数字
        match = re.search(r'CCTV[-_\s]*(\d+)', channel_name.upper())
        if match:
            # 找到数字，按数字排序
            num = int(match.group(1))
            return (0, num)  # 返回元组，0表示有数字，数字用于排序
        else:
            # 没有数字，按原名称排序
            return (1, channel_name)
    
    def run(self):
        """主函数"""
        print("=" * 60)
        print("IPTV直播源收集工具 - 最终优化版")
        print("=" * 60)
        
        all_channels = []
        
        # 1. 获取数据
        print("\n1. 获取数据...")
        for url in self.source_urls:
            content = self.fetch_content(url)
            if content:
                # 判断是否为M3U格式
                first_line = content.strip().split('\n')[0].strip() if content.strip() else ''
                if first_line.startswith('#EXTM3U'):
                    print(f"  检测到M3U格式，使用M3U解析器...")
                    channels_from_source = self.parse_m3u(content)
                    print(f"  从 {url} 解析到 {len(channels_from_source)} 个频道")
                else:
                    # 原有逐行解析
                    lines = content.split('\n')
                    channels_from_source = []
                    line_count = 0
                    for line in lines:
                        line_count += 1
                        channels_from_line = self.parse_line(line)
                        if channels_from_line:
                            channels_from_source.extend(channels_from_line)
                    print(f"  从 {url} 获取到 {line_count} 行数据，解析出 {len(channels_from_source)} 个频道")
        
                # 将本次源解析到的频道合并到总列表
                all_channels.extend(channels_from_source)
        
        if not all_channels:
            print("没有获取到任何有效数据！")
            return
        
        print(f"\n总计解析到 {len(all_channels)} 个频道")
        
        # 2. 去重（基于URL）
        print("\n2. 去重处理...")
        unique_channels = {}
        for channel in all_channels:
            url = channel['url']
            if url not in unique_channels:
                unique_channels[url] = channel
        
        unique_channels_list = list(unique_channels.values())
        print(f"去重后剩余 {len(unique_channels_list)} 个频道")
        
        # 3. 测试链接有效性
        valid_channels = self.test_links(unique_channels_list)
        
        if not valid_channels:
            print("\n没有有效的链接！")
            return
        
        # 4. 分类
        print("\n4. 分类整理...")
        categorized = defaultdict(list)
        for channel in valid_channels:
            category = self.categorize(channel['name'])
            categorized[category].append(channel)
        
        # 显示分类统计
        print("\n分类统计:")
        print("-" * 40)
        total_valid = 0
        for category in ["央视", "卫视", "地方台", "电影电视剧", "体育", "少儿动画", "其他"]:
            if category in categorized:
                count = len(categorized[category])
                total_valid += count
                print(f"  {category}: {count} 个频道")
        print(f"总计: {total_valid} 个有效频道")
        
        # 5. 保存文件
        print("\n5. 保存M3U文件...")
        channels_count, sources_count = self.save_m3u(categorized)
        
        print("\n" + "=" * 60)
        print("任务完成！")
        print(f"最终生成: {channels_count} 个频道，{sources_count} 个源")
        print("=" * 60)

# 运行脚本
if __name__ == "__main__":
    try:
        collector = FinalIPTV()
        collector.run()
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"\n程序运行出错: {e}")
        import traceback
        traceback.print_exc()

        input("\n按回车键退出...")
