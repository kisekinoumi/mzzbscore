import pandas as pd
import requests
from lxml import html
from openpyxl import load_workbook
import time
import sys
import re



# 定义 Anime 类，并增加更多的属性用于存储不同平台的数据
class Anime:
    def __init__(self, original_name, score_bgm='',score_bgm_vib='',score_bgm_sd='', score_al='', score_mal='', score_fm='',
                 bangumi_url='', anilist_url='', myanilist_url='', filmarks_url='',
                 bangumi_name='', anilist_name='', myanilist_name='', flimarks_name='',bangumi_total='',anilist_total='',myanilist_total='',filmarks_total=''):
        self.original_name = original_name  # 原始名称
        self.score_bgm = score_bgm  # Bangumi评分
        self.score_bgm_vib = score_bgm_vib  # Bangumi VIB评分
        self.score_bgm_sd = score_bgm_sd # Bangumi标准差
        self.score_al = score_al  # AniList评分
        self.score_mal = score_mal  # MyAnimeList评分
        self.score_fm = score_fm  # Filmarks评分
        self.bangumi_url = bangumi_url  # Bangumi条目链接
        self.anilist_url = anilist_url  # AniList条目链接
        self.myanilist_url = myanilist_url  # MyAnimeList条目链接
        self.filmarks_url = filmarks_url  # Filmarks条目链接
        self.bangumi_name = bangumi_name  # Bangumi名称
        self.anilist_name = anilist_name  # AniList名称
        self.myanilist_name = myanilist_name  # MyAnimeList名称
        self.flimarks_name = flimarks_name  # Filmarks名称
        self.bangumi_total = bangumi_total  # Bangumi评分人数
        self.anilist_total = anilist_total # AniList评分人数
        self.myanilist_total = myanilist_total # MyAnimeList评分人数
        self.filmarks_total = filmarks_total # Filmarks评分人数


    def __str__(self):
        return (f"Anime({self.original_name}, BGM: {self.score_bgm}, AL: {self.score_al}, "
                f"MAL: {self.score_mal}, FM: {self.score_fm}, "
                f"URLs: {self.bangumi_url}, {self.anilist_url}, {self.myanilist_url}, {self.filmarks_url}, "
                f"Names: {self.bangumi_name}, {self.anilist_name}, {self.myanilist_name}, {self.flimarks_name})")



try:
    # 读取Excel文件，假设文件名为test.xlsx
    file_path = 'mzzb.xlsx'
    wb = load_workbook(file_path)
    ws = wb.active
    df = pd.read_excel(file_path)
    # 定义 AniList GraphQL API 的URL
    anilist_url = 'https://graphql.anilist.co'

    # 遍历DataFrame中的每一行数据
    for index, row in df.iterrows():
        if pd.isna(row['原名']):
            print(f"Skipping row {index} because the original name is NaN.")
            continue  # 跳过这一行
        anime = Anime(original_name=row['原名'])  # 获取每行的“原名”列作为原始名称

        # URL编码处理动漫名称，避免特殊字符带来的问题
        keyword_encoded = requests.utils.quote(anime.original_name.encode('utf-8'))
        print(anime)
        try:
            # 1. 调用 Bangumi API 搜索条目
            search_url = f"https://api.bgm.tv/search/subject/{keyword_encoded}"
            # print(search_url)
            search_params = {
                'responseGroup': 'small',
                'type': 2  # 假设我们只关注动画类型的条目
            }
            search_response = requests.get(search_url, params=search_params)
            if search_response.status_code == 200:
                try:
                    search_data = search_response.json()
                except requests.exceptions.JSONDecodeError:
                    print(f"Error decoding JSON response for {anime.original_name}")
                    search_data = {}
            else:
                print(f"Failed to fetch Bangumi data for {anime.original_name}, status code: {search_response.status_code}")
                search_data = {}

            # 如果搜索结果包含列表且有条目
            if 'list' in search_data and search_data['list']:
                first_subject_id = search_data['list'][0]['id']  # 获取第一个条目的ID
                anime.bangumi_url = f"https://bgm.tv/subject/{first_subject_id}"  # 构造Bangumi条目URL
                anime.bangumi_name = search_data['list'][0].get('name', 'No name found')  # 获取Bangumi名称

                # 请求获取详细条目数据
                subject_url = f"https://api.bgm.tv/subject/{first_subject_id}"
                subject_response = requests.get(subject_url)
                subject_data = subject_response.json()

                # 如果存在评分信息，则保存评分，否则标记为未找到评分
                if 'rating' in subject_data and 'score' in subject_data['rating']:
                    print('bgm的页面评分'+str(subject_data['rating']['score']))
                    rating_counts = subject_data['rating']['count']
                    total_ratings = subject_data['rating']['total']

                    # 计算精确评分（平均分），保留四位小数
                    precise_score = sum(int(score) * int(count) for score, count in rating_counts.items()) / total_ratings
                    print('bgm的精确评分' + str(precise_score))
                    anime.score_bgm = round(precise_score, 2)
                    anime.score_bgm = f"{anime.score_bgm:.2f}"
                    anime.bangumi_total = str(total_ratings)

                    # 计算标准差
                    variance = sum(int(count) * (int(score) - (sum(int(score) * int(count) for score, count in rating_counts.items()) / total_ratings)) ** 2 for score, count in
                                   rating_counts.items()) / total_ratings
                    std_deviation = variance ** 0.5
                    anime.score_bgm_sd = f"{round(std_deviation, 3):.3f}"  # 保留三位小数

                    # --- 修改部分结束 ---

                else:
                    anime.score_bgm = 'No score available'
                print("bgm的链接:" + str(anime.bangumi_url))
                print("bgm的条目名字:" + str(anime.bangumi_name))
                print("bgm的评分:" + str(anime.score_bgm))
                print("bgm的评分人数:" + str(anime.bangumi_total))
                print("bgm的标准差:" + str(anime.score_bgm_sd))  # 打印标准差
                try:
                    vib_url = f"https://api.jirehlov.com/vib/{first_subject_id}"
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36 Edg/106.0.1370.42"
                    }
                    vib_response = requests.get(vib_url, headers=headers)
                    vib_response.raise_for_status()  # 如果请求失败，抛出异常

                    vib_data = vib_response.json()
                    anime.score_bgm_vib = vib_data.get("VIB_score", "No VIB score available")
                    anime.score_bgm_vib = round(float(anime.score_bgm_vib), 2)  # 保留两位小数
                    anime.score_bgm_vib = f"{anime.score_bgm_vib:.2f}"
                    print("bgm的VIB评分:" + str(anime.score_bgm_vib))

                except requests.exceptions.RequestException as e:
                    print(f"Error fetching VIB data for {anime.original_name}: {e}")
                    anime.score_bgm_vib = "Error fetching VIB data"
                except (KeyError, ValueError, TypeError) as e:
                    print(f"Error processing VIB data for {anime.original_name}: {e}")
                    anime.score_bgm_vib = "Error processing VIB data"
                # --- VIB API 调用代码结束 ---

            else:
                anime.score_bgm = 'No results found'  # 没有搜索到结果
                print(f"Failed to fetch Bangumi data for {anime.original_name}, status code: {search_response.status_code}")

            # 延时以避免频繁请求被拒绝
            time.sleep(1)
        except Exception as e:
            print(f"Error fetching Bangumi data for {anime.original_name}: {sys.exc_info()[0]}")


        # 2. 调用 MyAnimeList 页面搜索
        try:
            mal_search_url = f"https://myanimelist.net/anime.php?q={keyword_encoded}&cat=anime"
            mal_search_response = requests.get(mal_search_url)
            if mal_search_response.status_code == 200:
                mal_tree = html.fromstring(mal_search_response.content)
                try:
                    # 获取搜索结果中第一个条目的链接
                    anime_href = mal_tree.xpath('/html/body/div[1]/div[2]/div[3]/div[2]/div[6]/table/tr[2]/td[2]/div[1]/a[1]/@href')[0]
                    anime.myanilist_url = anime_href  # 存储MyAnimeList条目链接
                    mal_anime_response = requests.get(anime_href)
                    if mal_anime_response.status_code == 200:
                        mal_html_content = mal_anime_response.text
                        # mal_anime_tree = html.fromstring(mal_anime_response.content)
                        # print(html.tostring(mal_anime_tree, pretty_print=True).decode('utf-8'))
                        # 获取评分信息
                        # anime_mal_score = mal_anime_tree.xpath('/html/body/div[1]/div[2]/div[3]/div[2]/table/tr[1]/td[2]/div[1]/table/tr[1]/td/div[1]/div[1]/div[1]/div[1]/div[1]/div/text()')
                        # anime_mal_score = anime_mal_score[0].strip() if anime_mal_score else 'No score found'
                        anime_mal_score_match = re.search(r'<span itemprop="ratingValue" class="score-label score-\d+">([\d.]+)', mal_html_content)
                        anime_mal_score = str(anime_mal_score_match.group(1)) if anime_mal_score_match else None
                        anime.score_mal = anime_mal_score  # 保存评分
                        # 获取MyAnimeList的名称
                        # myanimelist_name = mal_anime_tree.xpath('/html/body/div[1]/div[2]/div[3]/div[1]/div/div[1]/div/h1/strong/text()')
                        # anime.myanilist_name = myanimelist_name[0].strip() if myanimelist_name else 'No name found'
                        myanimelist_name_match = re.search(r'<h1 class="title-name h1_bold_none"><strong>(.*?)</strong>', mal_html_content)
                        anime.myanilist_name = str(myanimelist_name_match.group(1).strip()) if myanimelist_name_match else None
                        # 获取MyAnimeList评分人数
                        mal_match = re.search(r'<span itemprop="ratingCount" style="display: none">(\d+)', mal_html_content)
                        if mal_match:
                            anime.myanilist_total = str(mal_match.group(1))
                        else:
                            anime.myanilist_total = 'No score found'
                    else:
                        anime.score_mal = 'No score found'
                    print("MAL的链接: " + str(anime.myanilist_url))
                    print("MAL的名称: " + str(anime.myanilist_name))
                    print("MAL的评分: " + str(anime.score_mal))
                    print("MAL的评分人数: " + str(anime.myanilist_total))
                except IndexError:
                    anime.score_mal = 'No href found'  # 没有找到条目链接
                    print(anime.score_mal)
            else:
                anime.score_mal = 'No results found'  # 请求失败
                print(anime.score_mal)
        except Exception as e:
            print(f"Error fetching MyAnimeList data for {anime.original_name}: {sys.exc_info()[0]}")

        try:

            # 3. 调用 AniList API 搜索
            anilist_search_query = '''
            query ($search: String) {
              Page (page: 1, perPage: 1) {
                media (search: $search, type: ANIME) {
                  id
                  title {
                    romaji
                  }
                }
              }
            }
            '''
            anilist_search_variables = {
                "search": anime.original_name  # 使用原始名称进行搜索
            }
            anilist_search_response = requests.post(anilist_url, json={'query': anilist_search_query, 'variables': anilist_search_variables})
            anilist_search_data = anilist_search_response.json()
            # 处理AniList API返回的数据
            if 'data' in anilist_search_data and 'Page' in anilist_search_data['data']:
                media_list = anilist_search_data['data']['Page']['media']
                if media_list:
                    first_anime_id = media_list[0]['id']  # 获取第一个条目的ID
                    anime.anilist_url = f"https://anilist.co/anime/{first_anime_id}"  # 构造AniList条目URL
                    anime.anilist_name = media_list[0]['title']['romaji']  # 获取AniList名称
                    # 请求获取详细评分信息
                    anilist_detail_query = '''
                    query ($id: Int) {
                      Media (id: $id) {
                        averageScore
                        popularity  
                      }
                    }
                    '''
                    anilist_detail_variables = {
                        "id": first_anime_id
                    }
                    anilist_detail_response = requests.post(anilist_url, json={'query': anilist_detail_query,
                                                                               'variables': anilist_detail_variables})
                    anilist_detail_data = anilist_detail_response.json()

                    # 处理AniList API返回的数据
                    if 'data' in anilist_detail_data and 'Media' in anilist_detail_data['data']:
                        anime_detail = anilist_detail_data['data']['Media']
                        anime.score_al = anime_detail.get('averageScore', 'No score found')
                        anime.anilist_total = anime_detail.get('popularity', 'No popularity info')  # 存储受欢迎度
                        anime.anilist_total = str(anime.anilist_total)
                    else:
                        anime.score_al = 'No AniList results'
                        anime.popularity = 'No popularity info'
                print("AniList的链接: " + str(anime.anilist_url))
                print("AniList的名称: " + str(anime.anilist_name))
                print("AniList的评分: " + str(anime.score_al))
                print("AniList的评分人数: " + str(anime.anilist_total))
            else:
                anime.score_al = 'Error with AniList API'  # API请求出错
                print(anime.score_al)
        except Exception as e:
            print(f"Error fetching AniList data for {anime.original_name}: {sys.exc_info()[0]}")

        try:
            # 4. 调用 Filmarks API 搜索
            filmarks_url = f"https://filmarks.com/search/animes?q={keyword_encoded}"
            filmarks_response = requests.get(filmarks_url)
            if filmarks_response.status_code == 200:
                filmarks_tree = html.fromstring(filmarks_response.content)
                try:
                    # 获取评分信息
                    anime_fm_score = filmarks_tree.xpath('/html/body/div[3]/div[3]/div[2]/div[1]/div[2]/div/div[1]/div[2]/div[3]/div/div[2]/text()')
                    anime.score_fm = anime_fm_score[0].strip() if anime_fm_score else 'No score found'
                    anime.filmarks_url = filmarks_url  # 存储Filmarks URL
                    # 获取Filmarks名称
                    filmarks_name = filmarks_tree.xpath('/html/body/div[3]/div[3]/div[2]/div[1]/div[2]/div/div[1]/div[2]/div[1]/h3/text()')
                    anime.flimarks_name = filmarks_name[0].strip() if filmarks_name else 'No name found'
                    # 获取Filmarks评分人数
                    filmarks_total = filmarks_tree.xpath('/html/body/div[3]/div[3]/div[2]/div[1]/div[2]/div/div[1]/div[1]/div[2]/div[1]/a/span/text()')
                    print(filmarks_total)
                    anime.filmarks_total = filmarks_total[0].strip() if filmarks_total else 'No name found'
                    print("Filmarks的链接: " + str(anime.filmarks_url))
                    print("Filmarks的名称: " + str(anime.flimarks_name))
                    print("Filmarks的评分: " + str(anime.score_fm))
                    print("Filmarks的评分人数: " + str(anime.filmarks_total))
                except IndexError:
                    anime.score_fm = 'No Filmarks score found'  # 没有找到评分
                    print(anime.score_fm)
            else:
                anime.score_fm = 'No Filmarks results'  # Filmarks请求失败
        except Exception as e:
            print(f"Error fetching Filmarks data for {anime.original_name}: {sys.exc_info()[0]}")

        # 更新Excel行数据
        current_row = ws[index + 2]  # DataFrame是从0开始的，而Excel是从1开始的，且第一行通常是表头
        if current_row[0].value == anime.original_name:  # 匹配原始名称
            try:
                current_row[2].value = float(anime.score_bgm) if anime.score_bgm not in ['No score available', 'No results found', '', None] else None
            except ValueError:
                current_row[2].value = None
            try:
                current_row[3].value = float(anime.bangumi_total) if anime.bangumi_total not in ['No score available', 'No results found', '', None] else None
            except ValueError:
                current_row[3].value = None
            try:
                current_row[4].value = float(anime.score_bgm_vib) if anime.score_bgm_vib not in ['Error processing VIB data','', None] else None
            except ValueError:
                current_row[4].value = None
            try:
                current_row[5].value = float(anime.score_bgm_sd) if anime.score_bgm_sd not in ['', None] else None
            except ValueError:
                current_row[5].value = None
            try:
                current_row[6].value = float(anime.score_al) / 10 if anime.score_al not in ['No score found','No score available','No results found', 'No AniList results','Error with AniList API','', None] else None
            except ValueError:
                current_row[6].value = None
            try:
                current_row[7].value = float(anime.anilist_total) if anime.anilist_total not in ['No score found','No score available','No results found', 'No AniList results','Error with AniList API','', None] else None
            except ValueError:
                current_row[7].value = None
            try:
                current_row[8].value = float(anime.score_mal) if anime.score_mal not in ['No href found',
                                                                                         'No score found',
                                                                                         'No score available',
                                                                                         'No results found', '',
                                                                                         None] else None
            except ValueError:
                current_row[8].value = None
            try:
                current_row[9].value = float(anime.myanilist_total) if anime.myanilist_total not in [
                    'No href found', 'No score found', 'No score available', 'No results found', '', None] else None
            except ValueError:
                current_row[9].value = None
            try:
                current_row[10].value = float(anime.score_fm) if anime.score_fm not in ['No score available',
                                                                                        'No results found',
                                                                                        'No Filmarks score found',
                                                                                        'No Filmarks results',
                                                                                        'N/A', '', None] else None
            except ValueError:
                current_row[10].value = None
            try:
                current_row[11].value = float(anime.score_fm) * 2 if anime.score_fm not in ['No score available',
                                                                                            'No results found',
                                                                                            'No Filmarks score found',
                                                                                            'No Filmarks results',
                                                                                            'N/A', '',
                                                                                            None] else None  # 保持与之前列数一致
            except ValueError:
                current_row[11].value = None
            try:
                current_row[12].value = anime.filmarks_total if anime.filmarks_total not in ['No score available',
                                                                                             'No results found',
                                                                                             'No Filmarks score found',
                                                                                             'No Filmarks results',
                                                                                             'N/A', '',
                                                                                             None] else None  # 保持与之前列数一致
            except ValueError:
                current_row[12].value = None
            try:
                # 写入名称并设置超链接
                current_row[15].value = anime.bangumi_name if anime.bangumi_name not in ['No name found',
                                                                                         None] else None  # 由于表格修改，列数变更
                if anime.bangumi_url:
                    ws.cell(row=index + 2, column=16).hyperlink = anime.bangumi_url
            except Exception as e:
                print(f"Error writing Bangumi data for {anime.original_name}: {sys.exc_info()[0]}")
            try:
                current_row[16].value = anime.anilist_name if anime.anilist_name not in ['No name found',
                                                                                         None] else None  # 由于表格修改，列数变更
                if anime.anilist_url:
                    ws.cell(row=index + 2, column=17).hyperlink = anime.anilist_url
            except Exception as e:
                print(f"Error writing AniList data for {anime.original_name}: {sys.exc_info()[0]}")
            try:
                current_row[17].value = anime.myanilist_name if anime.myanilist_name not in ['No name found',
                                                                                             None] else None  # 由于表格修改，列数变更
                if anime.myanilist_url:
                    ws.cell(row=index + 2, column=18).hyperlink = anime.myanilist_url
            except Exception as e:
                print(f"Error writing MyAnimeList data for {anime.original_name}: {sys.exc_info()[0]}")
            try:
                current_row[18].value = anime.flimarks_name if anime.flimarks_name not in ['No name found',
                                                                                           None] else None  # 由于表格修改，列数变更
                if anime.filmarks_url:
                    ws.cell(row=index + 2, column=19).hyperlink = anime.filmarks_url
            except Exception as e:
                print(f"Error writing Filmarks data for {anime.original_name}: {sys.exc_info()[0]}")
        print(anime)
    # # 保存更新后的Excel文件
    # wb.save(file_path)
    # print("Excel表格已成功更新。")

except Exception as e:
    print(f"发生错误: {e}")

finally:
    try:
        wb.save(file_path)
        print("Excel表格已成功更新。")
    except Exception as e:
        print(f"保存Excel文件时发生错误: {e}")
    while True:
        user_input = input("输入 'exit' 退出程序: ")
        if user_input.lower() == 'exit':  # 忽略大小写，允许 'exit' 退出
            break
    print("程序已退出...")