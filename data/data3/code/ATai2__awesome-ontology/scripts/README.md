# 维护脚本

三个脚本均只依赖 Python 标准库，Python 3.9 及以上可直接运行，无需安装依赖。

## generate_toc.py

重新生成 `README.md` 中的目录。目录写在 `<!-- START_TOC -->` 与 `<!-- END_TOC -->` 两个标记之间，只收录二级与三级标题，锚点按 GitHub 的规则生成（小写、去标点、空格转连字符）。

```bash
python scripts/generate_toc.py            # 就地更新目录
python scripts/generate_toc.py --check    # 只检查是否过期，CI 用
python scripts/generate_toc.py --file docs/other.md
```

## stats.py

输出清单的健康指标：小节数、条目数、唯一链接数、跨小节引用、域名分布，以及格式问题（缺描述、描述过长、以句号结尾、同一小节内重复链接）。

```bash
python scripts/stats.py
python scripts/stats.py --max-length 120
```

存在格式问题时退出码为 1，可直接挂到 CI。

## check_links.py

并发检查清单里所有 http(s) 链接的可达性。先发 HEAD 请求，服务器不接受时回退为带 Range 的小范围 GET，尽量减少误报。

```bash
python scripts/check_links.py                                  # 默认 16 并发，20 秒超时
python scripts/check_links.py --workers 32 --timeout 25
python scripts/check_links.py --json reports/links.json         # 输出机器可读报告
python scripts/check_links.py --file CONTRIBUTING.md            # 检查其他文件
```

被检查的链接从代码块以外的内容中提取，同一 URL 只请求一次。`scripts/ignore-links.txt` 中登记的 URL 会被跳过，用于放行需要登录、强反爬或临时故障的站点。

存在失效链接时退出码为 1，`--no-fail` 可以忽略退出码。
