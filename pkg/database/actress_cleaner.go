package database

import (
	"fmt"
	"slices"
	"strings"
)

type ActressCleaner struct {
	blockedExact map[string]struct{}
	protected    map[string]struct{}
}

type ActressCleanupChange struct {
	Code    string   `json:"code"`
	Before  []string `json:"before"`
	After   []string `json:"after"`
	Removed []string `json:"removed"`
}

type ActressCleanupReport struct {
	ScannedVideos    int                    `json:"scanned_videos"`
	ChangedVideos    int                    `json:"changed_videos"`
	RemovedActresses int                    `json:"removed_actresses"`
	Changes          []ActressCleanupChange `json:"changes"`
}

func NewActressCleaner() *ActressCleaner {
	return &ActressCleaner{
		blockedExact: toStringSet(
			"ゆうきすず", "周年だよん", "限界突破", "スペンス乳腺", "デビュー", "コスプ", "ミルクラ", "乳首",
			"ウブ女生徒に好かれ理性なくし", "濃密セックス", "交わる体液", "日間", "大好き東雲みれいが",
			"顔射の美学", "おねだりチ", "絶対", "汗だ", "白くて", "可愛い", "優しい", "いつ", "惚れて",
			"照れて", "男クンのお宅に", "快感に逆らえずビックンガック", "気が弱い", "よりシコい女体",
			"おっ", "メイド", "気持", "普通", "童貞君チ", "ヨダレだらだらナースの接吻と",
			"担任教師の僕は生徒の誘惑に負", "澪が気持ちよ", "主人", "の指マンがストライクすぎ",
			"無防備すぎる幼馴染のノーブラ", "ビンビン敏感チクビを澪が優", "究極の美肌スレンダー肉体の質",
			"嫁の連れ子を", "週間お貸ししま", "みおっち激しゃぶフェラフェラ", "日曜の朝", "寝起きの澪が可愛く",
			"奇跡", "舐めるのスキだからベロベロ", "スプラッシュ雫葉",
			"スレンダー女子マネージャーは", "セックスが本当に好きな", "ねっちょりセックスに溺れる文",
			"ポルチオ開発おま", "ある夏の熱帯夜", "一ヶ月禁欲し", "台本一切無し", "再婚相", "唾液マ",
			"究極性交", "手を繋", "小さい頃", "クリエイト", "種の媚", "応募", "体験撮影", "初撮り",
			"無限聖水", "ドスケベ乳", "プレステージ専属デビュ", "絶対忠実秘書", "風俗タワー", "性感フルコース",
			"唇が溶けるほどのベロキス性交", "天然成分由来", "リミットブレイク", "憑依バカッター",
			"絶頂ランジェリーナ", "美少女と", "貸し切り温泉と", "婚前カノジョが完堕ちするまで",
			"お貸ししま", "新・絶対的美少女", "新人",
		),
		protected: toStringSet("瀧本雫葉", "蒼乃美月", "綾瀬天", "東雲すみれ", "五芭", "天然美月"),
	}
}

func (c *ActressCleaner) CleanActresses(actresses []string) ([]string, []string) {
	present := make(map[string]struct{}, len(actresses))
	for _, actress := range actresses {
		trimmed := strings.TrimSpace(actress)
		if trimmed != "" {
			present[trimmed] = struct{}{}
		}
	}

	cleaned := make([]string, 0, len(actresses))
	removed := make([]string, 0)
	seen := make(map[string]struct{}, len(actresses))

	for _, actress := range actresses {
		trimmed := strings.TrimSpace(actress)
		if trimmed == "" {
			continue
		}
		if c.shouldRemove(trimmed, present) {
			removed = append(removed, trimmed)
			continue
		}
		if _, exists := seen[trimmed]; exists {
			removed = append(removed, trimmed)
			continue
		}
		seen[trimmed] = struct{}{}
		cleaned = append(cleaned, trimmed)
	}

	return cleaned, removed
}

func (c *ActressCleaner) ApplyToDatabase(db *JSONDatabase, write bool) (*ActressCleanupReport, error) {
	if db == nil {
		return nil, fmt.Errorf("db cannot be nil")
	}

	videos, err := db.GetAllVideos()
	if err != nil {
		return nil, err
	}

	report := &ActressCleanupReport{
		Changes: make([]ActressCleanupChange, 0),
	}

	for _, video := range videos {
		report.ScannedVideos++

		cleaned, removed := c.CleanActresses(video.Actresses)
		if slices.Equal(cleaned, video.Actresses) {
			continue
		}

		report.ChangedVideos++
		report.RemovedActresses += len(removed)
		report.Changes = append(report.Changes, ActressCleanupChange{
			Code:    video.GetCode(),
			Before:  slices.Clone(video.Actresses),
			After:   cleaned,
			Removed: removed,
		})

		if !write {
			continue
		}
		updatedVideo := *video
		updatedVideo.Actresses = slices.Clone(cleaned)
		if err := db.UpdateVideo(video.GetCode(), &updatedVideo); err != nil {
			return nil, err
		}
	}

	return report, nil
}

func (c *ActressCleaner) shouldRemove(name string, present map[string]struct{}) bool {
	if _, ok := c.protected[name]; ok {
		return false
	}
	if _, ok := c.blockedExact[name]; ok {
		return true
	}
	if isAllAsterisks(name) {
		return true
	}
	if name == "三田" {
		_, hasCanonical := present["三田真鈴"]
		return hasCanonical
	}
	if c.isProtectedNameContamination(name, present) {
		return true
	}
	return isRepeatedConcatenation(name, present)
}

func (c *ActressCleaner) isProtectedNameContamination(name string, present map[string]struct{}) bool {
	for protectedName := range c.protected {
		if name == protectedName {
			continue
		}
		if _, exists := present[protectedName]; !exists {
			continue
		}
		if strings.Contains(name, protectedName) {
			return true
		}
	}
	return false
}

// isAllAsterisks 判斷是否為全形或半形星號組成的垃圾值（如 ＊＊＊、***）。
func isAllAsterisks(name string) bool {
	if name == "" {
		return false
	}
	for _, r := range name {
		if r != '＊' && r != '*' {
			return false
		}
	}
	return true
}

func isRepeatedConcatenation(name string, present map[string]struct{}) bool {
	runes := []rune(name)
	if len(runes) < 2 || len(runes)%2 != 0 {
		return false
	}

	half := len(runes) / 2
	left := string(runes[:half])
	right := string(runes[half:])
	if left != right {
		return false
	}
	_, exists := present[left]
	return exists
}

func toStringSet(values ...string) map[string]struct{} {
	result := make(map[string]struct{}, len(values))
	for _, value := range values {
		result[value] = struct{}{}
	}
	return result
}
