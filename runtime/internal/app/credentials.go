package app

// credentials.go — 「登录到公司服务器」的本地凭据。
//
// # 存的是什么
//
// 服务器地址 + 一个**短期、可吊销的 token**。
// **不是 LLM 密钥**——方案 B 的关键就是真 key 只在服务器，
// 工程师机器上任何文件都找不到它。这一点在这里必须写清，
// 否则以后有人会顺手往这个文件里塞 key。
//
// # 放哪
//
// ~/.easycirq/credentials.json（权限 0600）。不放共享目录：
// 共享目录里放每个人的 token，等于把所有人的凭据集中泄露一次。
//
// # 它改变什么
//
// 没有这个文件 = 完全等于以前（连本机 daemon）。
// 有这个文件 = 命令直接发到 <server>/action，不再找本机 daemon。
// 这条判定集中在 loadCredentials，只有一个地方。

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// credentialsPath 允许测试覆盖。
const envCredentials = "EASYCIRQ_CREDENTIALS"

// Credentials 是登录后保存的凭据。
type Credentials struct {
	// Server 形如 https://easycirq.company.com（不带结尾斜杠）。
	Server string `json:"server"`
	// Token 是公司发的短期凭据。
	Token string `json:"token"`
	// Engineer 只用于展示，方便确认登录的是谁。
	Engineer string `json:"engineer,omitempty"`
}

func credentialsFile() string {
	if p := strings.TrimSpace(os.Getenv(envCredentials)); p != "" {
		return p
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return ""
	}
	return filepath.Join(home, ".easycirq", "credentials.json")
}

// loadCredentials 读凭据。第二个返回值表示是否真的登录了远端。
//
// **文件存在但内容不合法时返回 false 并给出警告**，不静默回落到本机：
// 那样工程师会以为自己连的是公司服务器，其实在操作本机窗口——
// 正是这个项目一路在防的那类"看起来对了其实没对"。
func loadCredentials() (Credentials, bool, error) {
	path := credentialsFile()
	if path == "" {
		return Credentials{}, false, nil
	}
	data, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return Credentials{}, false, nil
	}
	if err != nil {
		return Credentials{}, false, fmt.Errorf("读取凭据失败: %w", err)
	}
	var c Credentials
	if err := json.Unmarshal(data, &c); err != nil {
		return Credentials{}, false,
			fmt.Errorf("凭据文件损坏（%s）: %w —— 重新运行 easycirq login", path, err)
	}
	if strings.TrimSpace(c.Server) == "" || strings.TrimSpace(c.Token) == "" {
		return Credentials{}, false,
			fmt.Errorf("凭据文件缺少 server 或 token（%s）—— 重新运行 easycirq login", path)
	}
	c.Server = strings.TrimRight(strings.TrimSpace(c.Server), "/")
	c.Token = strings.TrimSpace(c.Token)
	return c, true, nil
}

// saveCredentials 写凭据，权限 0600。
func saveCredentials(c Credentials) (string, error) {
	path := credentialsFile()
	if path == "" {
		return "", errors.New("无法确定用户目录，不能保存凭据")
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return "", err
	}
	data, err := json.MarshalIndent(c, "", "  ")
	if err != nil {
		return "", err
	}
	// 先写临时文件再改名：中途失败不会留下半个凭据文件。
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, append(data, '\n'), 0o600); err != nil {
		return "", err
	}
	if err := os.Rename(tmp, path); err != nil {
		_ = os.Remove(tmp)
		return "", err
	}
	return path, nil
}

// clearCredentials 退出登录。
func clearCredentials() error {
	path := credentialsFile()
	if path == "" {
		return nil
	}
	err := os.Remove(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	return err
}
