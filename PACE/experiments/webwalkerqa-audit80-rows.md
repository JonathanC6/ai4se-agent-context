# WebWalkerQA 本机 80 题逐题审计

每行链接指向本机原轨迹。来源命中按有正文的 visit 去重，计入请求 URL 与缓存记录的最终 URL；忽略协议、www、末尾斜杠和段落锚点，保留查询参数。候选池根据该题实际加载的缓存页链接重建。菜单仅计 search 或 visit 明确列出的链接。其他 URL 也可能提供等价证据。

每道错题选取一个待核验的参考事实或一组代表词。括号列出大小写及 Unicode 规范化后，在该题**实际送入提取器的正文窗口**和**提取器返回文本**中命中的块。命中可能是导航词、重复题干、不同年份或否定语句，未命中可能是同义改写。线索用于定位，保留原始评分。

|题号|原判|标注页读到/总数|标注页线索|待核验词（任一）|正文 / 提取返回|复核笔记|
|---:|---|---:|---|---|---|---|
|[1](../results/webwalkerqa-full/rep-1/pace/row-1.json)|错|0/1|已加载页未发现|18 months / 18-month / eighteen months|— / —|替代项目页只给 2022-09 至 2024-02。C11 提取器写成 17 个月；答案保留这个数，同时解释按月份含首尾是 18 个月。也少了开始日。|
|[2](../results/webwalkerqa-full/rep-1/pace/row-2.json)|对|1/1|已读全部|—|— / —|预测与参考相符。|
|[3](../results/webwalkerqa-full/rep-1/pace/row-3.json)|错|0/1|已加载页未发现|five votes / five members / 5 votes / five council / 5 council|— / —|入口 HTTP 429。|
|[4](../results/webwalkerqa-full/rep-1/pace/row-4.json)|错|0/1|已加载页未发现|financial goal|— / —|未回答目标财务事项。|
|[5](../results/webwalkerqa-full/rep-1/pace/row-5.json)|错|0/1|已加载页未发现|tanzania / 坦桑尼亚|— / —|visit 返回空正文。|
|[6](../results/webwalkerqa-full/rep-1/pace/row-6.json)|对|2/2|已读全部|—|— / —|预测与参考相符。|
|[7](../results/webwalkerqa-full/rep-1/pace/row-7.json)|对|2/2|已读全部|—|— / —|预测与参考相符。|
|[8](../results/webwalkerqa-full/rep-1/pace/row-8.json)|错|0/2|已发现未展示|james hill / gregory r. heim / gregory heim|— / —|未给出两个年份的获奖者。|
|[9](../results/webwalkerqa-full/rep-1/pace/row-9.json)|错|2/2|已读全部|xiyan fu|C2 / C2|官网 C2 列出两名 chairs，C3 给补助日期；两块作答时均为 FULL。参考只列 Xiyan Fu。|
|[10](../results/webwalkerqa-full/rep-1/pace/row-10.json)|错|1/2|已读部分|dragan ahmetovic / fernando loizides|— / —|缺历史候选人姓名，访问投票历史页面仍不足。|
|[11](../results/webwalkerqa-full/rep-1/pace/row-11.json)|错|1/2|已读部分|john knight|— / —|找到软件检查议程及 Laitenberger；缺安全关键系统主题的 John Knight。|
|[12](../results/webwalkerqa-full/rep-1/pace/row-12.json)|错|1/2|已读部分|10:30 / 22:30|C2、C3 / C3|C3 写明 7 月 11 日晚时段，最终也复述；代理把 7 月 10 日 Spotlights 选为主答案。C2、C3 均为 FULL。|
|[13](../results/webwalkerqa-full/rep-1/pace/row-13.json)|对|2/2|已读全部|—|— / —|预测与参考相符。|
|[14](../results/webwalkerqa-full/rep-1/pace/row-14.json)|对|2/2|已读全部|—|— / —|预测与参考相符。|
|[15](../results/webwalkerqa-full/rep-1/pace/row-15.json)|错|0/2|已加载页未发现|70,000 / 70000 / 70 thousand / 50 million|— / —|未给出供水受益人数和基金规模。|
|[16](../results/webwalkerqa-full/rep-1/pace/row-16.json)|错|1/2|已读部分|dream world 3 / 梦想世界3 / 梦想世界三 / 万仙逐鹿|C2、C4、C6、C7、C9、C11、C13、C14 / C7、C9、C11、C14|页面中有游戏名，但产品目录不能证明获奖或开测日期。|
|[17](../results/webwalkerqa-full/rep-1/pace/row-17.json)|错|0/2|已加载页未发现|65,000 / 65000 / 1,009|— / —|入口 HTTP 403。|
|[18](../results/webwalkerqa-full/rep-1/pace/row-18.json)|错|0/2|已加载页未发现|linirean / dwarves / dwarfs|— / —|未取得活动角色及宝藏种类。|
|[19](../results/webwalkerqa-full/rep-1/pace/row-19.json)|错|1/2|已读部分|ocean conservation / protect the ocean / 海洋保|C2、C7 / C7|最终回答含为儿童圆梦和海洋环保的具体例子，也把地震救灾并入主题；题目只要两项。评分有口径争议。|
|[20](../results/webwalkerqa-full/rep-1/pace/row-20.json)|错|0/1|曾展示未读|4.4 million / 4,400,000 / 4.4m|— / —|目标链接在 C4/C5 菜单出现；C5 作答时仍为 FULL。ReAct 打开该新闻读到 440 万。|
|[21](../results/webwalkerqa-full/rep-1/pace/row-21.json)|错|0/1|已发现未展示|14 february 2025 / february 14, 2025 / 2025-02-14|— / —|用较新会议列表否定历史会议，目标页未在可见菜单出现。|
|[22](../results/webwalkerqa-full/rep-1/pace/row-22.json)|错|0/1|已发现未展示|mike gorman / michael gorman|— / —|未给出 Mike Gorman。|
|[23](../results/webwalkerqa-full/rep-1/pace/row-23.json)|对|1/1|已读全部|—|— / —|参考给出教程标题，题干问建模语言；回答给出标题及 Spider diagrams。原裁判给对。|
|[24](../results/webwalkerqa-full/rep-1/pace/row-24.json)|错|1/1|已读全部|early november / november 2024|— / —|读到标注 URL，但 C5 的访问结果是 2027 年旅行信息，不能回答 2024 签证问题。|
|[25](../results/webwalkerqa-full/rep-1/pace/row-25.json)|错|0/2|已加载页未发现|november 22 / nov 22 / october 28 / oct 28|C1、C10、C13 / C1、C3、C10、C13|出现了类似截止日期，却来自不同届次。|
|[26](../results/webwalkerqa-full/rep-1/pace/row-26.json)|对|2/2|已读全部|—|— / —|预测与参考相符。|
|[27](../results/webwalkerqa-full/rep-1/pace/row-27.json)|错|0/2|已发现未展示|chris tang / christopher tang|C1、C17 / —|替代正文中的 Chris Tang 是董事会名单，不能证明是 2011 Fellow；未给出获奖者。|
|[28](../results/webwalkerqa-full/rep-1/pace/row-28.json)|错|1/2|已读部分|đàn bầu / dan bau / đàn bâu / monochord|— / —|答出 Gugak，缺越南乐器。|
|[29](../results/webwalkerqa-full/rep-1/pace/row-29.json)|错|2/2|已读全部|transition from relief to development|— / C1、C2、C3、C6|付款截止日正确；当前委员会页面不支持历史议题对应，C6/C7 为 FULL。|
|[30](../results/webwalkerqa-full/rep-1/pace/row-30.json)|错|1/2|已读部分|november 14 / nov. 14 / nov 14|— / —|页面版本未给 2024 新闻禁发时间。|
|[31](../results/webwalkerqa-full/rep-1/pace/row-31.json)|错|0/2|已加载页未发现|szlufarska|C5 / C2、C5|人名已在题干中；看到董事名单不能判断教育协作主张。|
|[32](../results/webwalkerqa-full/rep-1/pace/row-32.json)|错|0/2|已加载页未发现|last continent / dernier continent|— / —|未找到指定纪录片。|
|[33](../results/webwalkerqa-full/rep-1/pace/row-33.json)|错|1/2|已读部分|fan demand / classic angry birds / classic games|C7 / C2、C6、C7、C11|找到保护项目，未证实复刻经典游戏与粉丝需求。|
|[35](../results/webwalkerqa-full/rep-1/pace/row-35.json)|错|0/2|已加载页未发现|隐私攻击 / 白质纤维|— / —|24 步无最终答案。|
|[36](../results/webwalkerqa-full/rep-1/pace/row-36.json)|错|0/2|已加载页未发现|科研成果证明 / 资格审查|C6 / C6|用 2025 材料讨论 2023/2024，未完成跨年比较。|
|[37](../results/webwalkerqa-full/rep-1/pace/row-37.json)|错|0/2|已加载页未发现|6月30 / 六月三十|— / —|仅找到一位报告人的日期。|
|[38](../results/webwalkerqa-full/rep-1/pace/row-38.json)|错|0/2|已加载页未发现|13.2|— / —|未给出正确季度营收降幅。|
|[39](../results/webwalkerqa-full/rep-1/pace/row-39.json)|对|1/1|已读全部|—|— / —|预测与参考相符。|
|[40](../results/webwalkerqa-full/rep-1/pace/row-40.json)|对|1/1|已读全部|—|— / —|预测与参考相符。|
|[42](../results/webwalkerqa-full/rep-1/pace/row-42.json)|错|0/1|已加载页未发现|旋转木马 / carousel|— / —|未给出所问更新元素。|
|[43](../results/webwalkerqa-full/rep-1/pace/row-43.json)|错|0/1|已加载页未发现|2009|— / —|24 步无最终答案。|
|[44](../results/webwalkerqa-full/rep-1/pace/row-44.json)|对|0/1|已加载页未发现|—|— / —|替代来源也能答对。|
|[45](../results/webwalkerqa-full/rep-1/pace/row-45.json)|错|0/1|已加载页未发现|4:30 / 04:30|— / —|未给出上海本地时段。|
|[46](../results/webwalkerqa-full/rep-1/pace/row-46.json)|错|0/1|已加载页未发现|ehninger|— / —|未给出医生姓名。|
|[47](../results/webwalkerqa-full/rep-1/pace/row-47.json)|错|0/1|已加载页未发现|quiles lara|— / —|缺人名与上任日。|
|[48](../results/webwalkerqa-full/rep-1/pace/row-48.json)|错|0/1|已加载页未发现|april 2022 / 2022年4月|— / —|缺项目启动年月。|
|[49](../results/webwalkerqa-full/rep-1/pace/row-49.json)|错|0/1|已加载页未发现|蒋斌|— / —|visit 返回空正文。|
|[50](../results/webwalkerqa-full/rep-1/pace/row-50.json)|错|1/2|已读部分|online trust & safety / online trust and safety|C3 / C3|参考主题在最终答案中。C3/C7 支持 13、14 日分别有主题日和教程；回答同时把三个主题称为两个。|
|[51](../results/webwalkerqa-full/rep-1/pace/row-51.json)|错|0/1|已加载页未发现|june 20, 2021 / 20 june 2021 / june 20th|— / —|未给出活动结束日。|
|[52](../results/webwalkerqa-full/rep-1/pace/row-52.json)|错|0/2|已加载页未发现|dragan ahmetovic|— / —|未给出 Dragan Ahmetovic。|
|[53](../results/webwalkerqa-full/rep-1/pace/row-53.json)|错|0/2|已加载页未发现|10月27 / 10 月 27|— / —|24 步无最终答案。|
|[54](../results/webwalkerqa-full/rep-1/pace/row-54.json)|错|0/2|已加载页未发现|代谢组学 / 微光成像|— / —|两家公司的技术及产业差异未找到。|
|[55](../results/webwalkerqa-full/rep-1/pace/row-55.json)|错|0/2|已加载页未发现|rural revitalization / 乡村振兴|— / —|入口 HTTP 403。|
|[58](../results/webwalkerqa-full/rep-1/pace/row-58.json)|错|0/2|已加载页未发现|northern kentucky convention center / northern kentucky convention centre|— / —|入口 HTTP 403。|
|[59](../results/webwalkerqa-full/rep-1/pace/row-59.json)|错|1/2|已读部分|cale passmore|— / —|答出邮箱，未答 Cale Passmore。|
|[60](../results/webwalkerqa-full/rep-1/pace/row-60.json)|错|1/2|已读部分|divesh|C2、C4 / C2|C5 glimpse 恢复含 Divesh 的 C2。第二张标注页未命中；根据另一张 trustees 名单选了 Sihem。|
|[64](../results/webwalkerqa-full/rep-1/pace/row-64.json)|错|1/2|已读部分|isle of pigs|— / —|答出地球日游戏；另一个名字以搜索猜测出现，回答没有确认。|
|[66](../results/webwalkerqa-full/rep-1/pace/row-66.json)|错|0/2|已加载页未发现|雨花台 / 南京抗日航空烈士|— / —|visit 返回空正文。|
|[68](../results/webwalkerqa-full/rep-1/pace/row-68.json)|错|0/2|已加载页未发现|33天 / 33 天 / 三十三天|— / —|未给出天数。|
|[69](../results/webwalkerqa-full/rep-1/pace/row-69.json)|错|0/2|已加载页未发现|广州 / guangzhou|— / —|未识别两座城市。|
|[70](../results/webwalkerqa-full/rep-1/pace/row-70.json)|错|0/2|已加载页未发现|孙国豪|— / —|未给出目标团队，对博士培养起始年份也未确认。|
|[71](../results/webwalkerqa-full/rep-1/pace/row-71.json)|错|0/2|已加载页未发现|蔡佳洪 / 叶洪帆 / 晏紫微|— / —|缺推荐名单与合作领域。|
|[73](../results/webwalkerqa-full/rep-1/pace/row-73.json)|错|0/2|已发现未展示|郑忠龙|C8 / —|C8 教师表有郑忠龙，未证实导师关系或教学奖。|
|[74](../results/webwalkerqa-full/rep-1/pace/row-74.json)|错|0/2|已加载页未发现|menhera / 七濑胡桃 / 御猫|— / —|未给出两个 IP 联动的具体内容。|
|[75](../results/webwalkerqa-full/rep-1/pace/row-75.json)|错|0/2|已加载页未发现|sky lantern / sky-lantern|— / —|所读页面主要是较新赛季，未找出两项资源获取方式。|
|[76](../results/webwalkerqa-full/rep-1/pace/row-76.json)|对|0/2|曾展示未读|—|— / —|从另一日程页找齐两个截止日。|
|[77](../results/webwalkerqa-full/rep-1/pace/row-77.json)|错|0/2|已加载页未发现|高应波|— / —|未锁定学生姓名。|
|[78](../results/webwalkerqa-full/rep-1/pace/row-78.json)|错|0/1|已加载页未发现|015 dlc for you|— / —|当前商店页面未给出历史实验名。|
|[80](../results/webwalkerqa-full/rep-1/pace/row-80.json)|对|1/1|已读全部|—|— / —|预测与参考相符。|
|[82](../results/webwalkerqa-full/rep-1/pace/row-82.json)|对|1/1|已读全部|—|— / —|预测与参考相符。|
|[83](../results/webwalkerqa-full/rep-1/pace/row-83.json)|错|0/1|已加载页未发现|21 solon|— / —|入口 HTTP 429。|
|[84](../results/webwalkerqa-full/rep-1/pace/row-84.json)|错|0/1|已加载页未发现|2000|— / —|教师简历及开始年份未找到。|
|[85](../results/webwalkerqa-full/rep-1/pace/row-85.json)|错|0/1|已加载页未发现|589,000 / 589000|— / —|未给出投票人数和慈善分成。|
|[87](../results/webwalkerqa-full/rep-1/pace/row-87.json)|错|0/1|已加载页未发现|30,000 ilv / 30000 ilv|— / —|入口 HTTP 429。|
|[88](../results/webwalkerqa-full/rep-1/pace/row-88.json)|错|0/1|已加载页未发现|博士英语课表 / 国际学生版|— / —|未给出 2015 年文件清单。|
|[89](../results/webwalkerqa-full/rep-1/pace/row-89.json)|错|0/1|已加载页未发现|corporate responsibility / corporate social responsibility|— / C1|组织社会责任词汇可出现在提取目标里，未取得相关评分及改进计划。|
|[92](../results/webwalkerqa-full/rep-1/pace/row-92.json)|错|0/1|已加载页未发现|cute accidence / flickering light|— / —|未给出 4 首曲名。|
|[94](../results/webwalkerqa-full/rep-1/pace/row-94.json)|对|1/2|已读部分|—|— / —|预测与参考相符。|
|[98](../results/webwalkerqa-full/rep-1/pace/row-98.json)|错|0/2|已加载页未发现|regenerative tourism / resilient tourism|C3 / —|C3 原网页输入含再生旅游与韧性生态两项；提取器强调未提海平面，漏掉措施。C3 作答时为 FULL。|
|[100](../results/webwalkerqa-full/rep-1/pace/row-100.json)|错|0/2|已加载页未发现|november 22 / nov. 22 / nov 22 / 11月22|— / —|回答使用其他折扣或更新信息，未给所问日期和倍率。|
