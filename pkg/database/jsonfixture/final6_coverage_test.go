package jsonfixture

import (
	"testing"

	. "actress-classifier/pkg/database"
)

// corruptIndexDB returns a loaded JSONDatabase whose index path is
// unwritable, so saveIndex fails and the writers exercise their
// warn-on-saveIndex-failure branches (without failing the operation).
func corruptIndexDB(t *testing.T) *JSONDatabase {
	t.Helper()
	db := loadedJSONDB(t)
	if err := db.AddVideo(&Video{Code: "IDX-SEED", Title: "s"}); err != nil {
		t.Fatalf("seed: %v", err)
	}
	db.mu.Lock()
	db.indexFile = "bad\x00index"
	db.mu.Unlock()
	return db
}

func TestAddVideo_SaveIndexFailureWarnsButSucceeds(t *testing.T) {
	db := corruptIndexDB(t)
	if err := db.AddVideo(&Video{Code: "IDX-1", Title: "a"}); err != nil {
		t.Errorf("AddVideo returned %v, want nil (saveIndex failure only warns)", err)
	}
	if _, err := db.GetVideo("IDX-1"); err != nil {
		t.Errorf("IDX-1 should be present despite index warn: %v", err)
	}
}

func TestUpdateVideo_SaveIndexFailureWarnsButSucceeds(t *testing.T) {
	db := corruptIndexDB(t)
	if err := db.UpdateVideo("IDX-SEED", &Video{Code: "IDX-SEED", Title: "u"}); err != nil {
		t.Errorf("UpdateVideo returned %v, want nil", err)
	}
}

func TestDeleteVideo_SaveIndexFailureWarnsButSucceeds(t *testing.T) {
	db := corruptIndexDB(t)
	if err := db.DeleteVideo("IDX-SEED"); err != nil {
		t.Errorf("DeleteVideo returned %v, want nil", err)
	}
}
