package database

import (
	"slices"
	"testing"
)

func TestActressCleaner_CleanActressesRemovesExactBlockedTokens(t *testing.T) {
	cleaner := NewActressCleaner()

	cleaned, removed := cleaner.CleanActresses([]string{"石川澪", "周年だよん", "限界突破"})

	assertStringSliceEqual(t, cleaned, []string{"石川澪"})
	assertStringSliceEqual(t, removed, []string{"周年だよん", "限界突破"})
}

func TestActressCleaner_CleanActressesKeepsApprovedNames(t *testing.T) {
	cleaner := NewActressCleaner()

	cleaned, removed := cleaner.CleanActresses([]string{"瀧本雫葉", "石川澪", "蒼乃美月", "綾瀬天", "東雲すみれ", "五芭", "天然美月"})

	assertStringSliceEqual(t, cleaned, []string{"瀧本雫葉", "石川澪", "蒼乃美月", "綾瀬天", "東雲すみれ", "五芭", "天然美月"})
	assertStringSliceEqual(t, removed, nil)
}

func TestActressCleaner_CleanActressesRemovesFragmentOnlyWhenCanonicalNameExists(t *testing.T) {
	cleaner := NewActressCleaner()

	cleaned, removed := cleaner.CleanActresses([]string{"三田真鈴", "三田"})

	assertStringSliceEqual(t, cleaned, []string{"三田真鈴"})
	assertStringSliceEqual(t, removed, []string{"三田"})
}

func TestActressCleaner_CleanActressesRemovesRepeatedConcatenatedNameWhenBaseExists(t *testing.T) {
	cleaner := NewActressCleaner()

	cleaned, removed := cleaner.CleanActresses([]string{"蒼乃美月", "蒼乃美月蒼乃美月"})

	assertStringSliceEqual(t, cleaned, []string{"蒼乃美月"})
	assertStringSliceEqual(t, removed, []string{"蒼乃美月蒼乃美月"})
}

func TestActressCleaner_CleanActressesRemovesTitleFragmentsFoundInShadowDB(t *testing.T) {
	cleaner := NewActressCleaner()

	cleaned, removed := cleaner.CleanActresses([]string{
		"絶頂ランジェリーナ",
		"美少女と",
		"瀧本雫葉",
		"瀧本雫葉汁",
		"婚前カノジョが完堕ちするまで",
		"新・絶対的美少女",
		"新人",
	})

	assertStringSliceEqual(t, cleaned, []string{"瀧本雫葉"})
	assertStringSliceEqual(t, removed, []string{
		"絶頂ランジェリーナ",
		"美少女と",
		"瀧本雫葉汁",
		"婚前カノジョが完堕ちするまで",
		"新・絶対的美少女",
		"新人",
	})
}

func TestActressCleaner_CleanActressesRemovesLongTitleFragments(t *testing.T) {
	cleaner := NewActressCleaner()

	cleaned, removed := cleaner.CleanActresses([]string{
		"アルバイト先の真面目なアノ娘",
		"ソープ部を新たにつくった生徒",
		"パンチラで誘惑するからかい上",
		"ヤリたい放題いいなり調教イカ",
		"ヤリまくり一泊二日の温泉旅行",
		"一夜を使い果たして朝陽が昇る",
		"初めてサレた快感が忘れられず",
		"可愛い顔した魔性少女がおっぱ",
		"同窓会でネトラレてるのにいっ",
		"地味メガネの書店員バイトちゃ",
		"帰省先のド田舎で僕の東京カノ",
		"引きニート喪女な妹のオナニー",
		"新型媚薬でキメセク洗脳美脚ガ",
		"田舎帰省で成長期の姪っ子と自",
		"入浴中の裸体を覗かれてから",
		"手でさするのは浮気にならな",
		"今日から澪がお前らの嫁",
	})

	assertStringSliceEqual(t, cleaned, nil)
	assertStringSliceEqual(t, removed, []string{
		"アルバイト先の真面目なアノ娘",
		"ソープ部を新たにつくった生徒",
		"パンチラで誘惑するからかい上",
		"ヤリたい放題いいなり調教イカ",
		"ヤリまくり一泊二日の温泉旅行",
		"一夜を使い果たして朝陽が昇る",
		"初めてサレた快感が忘れられず",
		"可愛い顔した魔性少女がおっぱ",
		"同窓会でネトラレてるのにいっ",
		"地味メガネの書店員バイトちゃ",
		"帰省先のド田舎で僕の東京カノ",
		"引きニート喪女な妹のオナニー",
		"新型媚薬でキメセク洗脳美脚ガ",
		"田舎帰省で成長期の姪っ子と自",
		"入浴中の裸体を覗かれてから",
		"手でさするのは浮気にならな",
		"今日から澪がお前らの嫁",
	})
}

func TestActressCleaner_CleanActressesReplacesKnownNameInTitleFragment(t *testing.T) {
	cleaner := NewActressCleaner()

	cleaned, removed := cleaner.CleanActresses([]string{"石川澪とラブラブでハメまくる"})

	assertStringSliceEqual(t, cleaned, []string{"石川澪"})
	assertStringSliceEqual(t, removed, []string{"石川澪とラブラブでハメまくる"})
}

func TestActressCleaner_CleanActressesReplacesKnownNameWithoutReportingExistingDuplicate(t *testing.T) {
	cleaner := NewActressCleaner()

	cleaned, removed := cleaner.CleanActresses([]string{"石川澪", "石川澪とラブラブでハメまくる"})

	assertStringSliceEqual(t, cleaned, []string{"石川澪"})
	assertStringSliceEqual(t, removed, []string{"石川澪とラブラブでハメまくる"})
}

func TestActressCleaner_ApplyToDatabaseDryRunDoesNotMutateData(t *testing.T) {
	db, _ := setupTestDB(t)
	video := NewVideo("ABF-062")
	video.Actresses = []string{"蒼乃美月", "顔射の美学", "蒼乃美月蒼乃美月"}
	if err := db.UpdateVideo("ABF-062", video); err != nil {
		t.Fatalf("Failed to seed video: %v", err)
	}

	cleaner := NewActressCleaner()
	report, err := cleaner.ApplyToDatabase(db, false)
	if err != nil {
		t.Fatalf("ApplyToDatabase returned error: %v", err)
	}

	if report.ChangedVideos != 1 {
		t.Fatalf("expected 1 changed video, got %d", report.ChangedVideos)
	}
	if report.RemovedActresses != 2 {
		t.Fatalf("expected 2 removed actresses, got %d", report.RemovedActresses)
	}

	reloaded, err := db.GetVideo("ABF-062")
	if err != nil {
		t.Fatalf("Failed to fetch video: %v", err)
	}
	assertStringSliceEqual(t, reloaded.Actresses, []string{"蒼乃美月", "顔射の美学", "蒼乃美月蒼乃美月"})
}

func TestActressCleaner_ApplyToDatabaseWriteMutatesData(t *testing.T) {
	db, _ := setupTestDB(t)
	video := NewVideo("ABF-177")
	video.Actresses = []string{"絶対", "瀧本雫葉", "リミットブレイク"}
	if err := db.UpdateVideo("ABF-177", video); err != nil {
		t.Fatalf("Failed to seed video: %v", err)
	}

	cleaner := NewActressCleaner()
	report, err := cleaner.ApplyToDatabase(db, true)
	if err != nil {
		t.Fatalf("ApplyToDatabase returned error: %v", err)
	}

	if report.ChangedVideos != 1 {
		t.Fatalf("expected 1 changed video, got %d", report.ChangedVideos)
	}
	if report.RemovedActresses != 2 {
		t.Fatalf("expected 2 removed actresses, got %d", report.RemovedActresses)
	}

	reloaded, err := db.GetVideo("ABF-177")
	if err != nil {
		t.Fatalf("Failed to fetch video: %v", err)
	}
	assertStringSliceEqual(t, reloaded.Actresses, []string{"瀧本雫葉"})
}

func assertStringSliceEqual(t *testing.T, got, want []string) {
	t.Helper()
	if got == nil {
		got = []string{}
	}
	if want == nil {
		want = []string{}
	}
	if !slices.Equal(got, want) {
		t.Fatalf("expected %#v, got %#v", want, got)
	}
}

func TestActressCleaner_RemovesFullWidthAsterisks(t *testing.T) {
	cleaner := NewActressCleaner()

	cleaned, removed := cleaner.CleanActresses([]string{"＊＊＊", "石川澪"})

	assertStringSliceEqual(t, cleaned, []string{"石川澪"})
	assertStringSliceEqual(t, removed, []string{"＊＊＊"})
}

func TestActressCleaner_RemovesHalfWidthAsterisks(t *testing.T) {
	cleaner := NewActressCleaner()

	cleaned, removed := cleaner.CleanActresses([]string{"***", "宇野みれい"})

	assertStringSliceEqual(t, cleaned, []string{"宇野みれい"})
	assertStringSliceEqual(t, removed, []string{"***"})
}

func TestActressCleaner_RemovesSingleAsterisk(t *testing.T) {
	cleaner := NewActressCleaner()

	cleaned, removed := cleaner.CleanActresses([]string{"＊", "天羽りりか"})

	assertStringSliceEqual(t, cleaned, []string{"天羽りりか"})
	assertStringSliceEqual(t, removed, []string{"＊"})
}
