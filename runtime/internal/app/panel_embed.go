package app

// panel_embed.go — 把面板页 embed 进二进制。
//
// 为什么 embed 而不是放到安装目录：客户机不该为了看一眼状态去装 node 或解一层
// 静态资源；embed 之后"装完就有"，也不可能出现"面板文件和二进制不匹配"。

import _ "embed"

//go:embed panel/index.html
var panelHTML []byte
