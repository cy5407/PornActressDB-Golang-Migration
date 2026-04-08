export namespace backend {
	
	export class ConflictItem {
	    source: string;
	    destination: string;
	
	    static createFrom(source: any = {}) {
	        return new ConflictItem(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.source = source["source"];
	        this.destination = source["destination"];
	    }
	}
	export class ScanResult {
	    path: string;
	    code: string;
	
	    static createFrom(source: any = {}) {
	        return new ScanResult(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.path = source["path"];
	        this.code = source["code"];
	    }
	}
	export class SearchResult {
	    code: string;
	    title: string;
	    studio: string;
	    release_date: string;
	    url: string;
	    actresses: string[];
	    method: string;
	    error?: string;
	    error_kind?: string;
	
	    static createFrom(source: any = {}) {
	        return new SearchResult(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.code = source["code"];
	        this.title = source["title"];
	        this.studio = source["studio"];
	        this.release_date = source["release_date"];
	        this.url = source["url"];
	        this.actresses = source["actresses"];
	        this.method = source["method"];
	        this.error = source["error"];
	        this.error_kind = source["error_kind"];
	    }
	}
	export class StudioInfo {
	    studio: string;
	
	    static createFrom(source: any = {}) {
	        return new StudioInfo(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.studio = source["studio"];
	    }
	}

}

export namespace database {
	
	export class Metadata {
	    source: string;
	    confidence: number;
	
	    static createFrom(source: any = {}) {
	        return new Metadata(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.source = source["source"];
	        this.confidence = source["confidence"];
	    }
	}
	export class VideoData {
	    code: string;
	    id?: string;
	    title: string;
	    studio: string;
	    studio_code?: string;
	    release_date: string;
	    url: string;
	    actresses: string[];
	    search_status: string;
	    last_search_date: string;
	    created_at: string;
	    updated_at: string;
	    metadata: Metadata;
	    original_filename?: string;
	    file_path?: string;
	    search_method?: string;
	
	    static createFrom(source: any = {}) {
	        return new VideoData(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.code = source["code"];
	        this.id = source["id"];
	        this.title = source["title"];
	        this.studio = source["studio"];
	        this.studio_code = source["studio_code"];
	        this.release_date = source["release_date"];
	        this.url = source["url"];
	        this.actresses = source["actresses"];
	        this.search_status = source["search_status"];
	        this.last_search_date = source["last_search_date"];
	        this.created_at = source["created_at"];
	        this.updated_at = source["updated_at"];
	        this.metadata = this.convertValues(source["metadata"], Metadata);
	        this.original_filename = source["original_filename"];
	        this.file_path = source["file_path"];
	        this.search_method = source["search_method"];
	    }
	
		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}

}

export namespace mover {
	
	export class MoveResult {
	    source: string;
	    destination: string;
	    success: boolean;
	    error?: string;
	    skipped?: boolean;
	    renamed?: string;
	
	    static createFrom(source: any = {}) {
	        return new MoveResult(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.source = source["source"];
	        this.destination = source["destination"];
	        this.success = source["success"];
	        this.error = source["error"];
	        this.skipped = source["skipped"];
	        this.renamed = source["renamed"];
	    }
	}
	export class BatchResult {
	    operation_id?: string;
	    total_items: number;
	    success_count: number;
	    failed_count: number;
	    skipped_count: number;
	    results: MoveResult[];
	    status?: string;
	    summary?: string;
	    duration: string;
	
	    static createFrom(source: any = {}) {
	        return new BatchResult(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.operation_id = source["operation_id"];
	        this.total_items = source["total_items"];
	        this.success_count = source["success_count"];
	        this.failed_count = source["failed_count"];
	        this.skipped_count = source["skipped_count"];
	        this.results = this.convertValues(source["results"], MoveResult);
	        this.status = source["status"];
	        this.summary = source["summary"];
	        this.duration = source["duration"];
	    }
	
		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}
	export class MergeResult {
	    source_dir: string;
	    dest_dir: string;
	    files_moved: number;
	    files_total: number;
	    errors?: MoveResult[];
	    success: boolean;
	    deleted_src: boolean;
	
	    static createFrom(source: any = {}) {
	        return new MergeResult(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.source_dir = source["source_dir"];
	        this.dest_dir = source["dest_dir"];
	        this.files_moved = source["files_moved"];
	        this.files_total = source["files_total"];
	        this.errors = this.convertValues(source["errors"], MoveResult);
	        this.success = source["success"];
	        this.deleted_src = source["deleted_src"];
	    }
	
		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}
	export class MoveItem {
	    source: string;
	    destination: string;
	    on_conflict?: string;
	
	    static createFrom(source: any = {}) {
	        return new MoveItem(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.source = source["source"];
	        this.destination = source["destination"];
	        this.on_conflict = source["on_conflict"];
	    }
	}
	export class MoveLog {
	    source: string;
	    destination: string;
	    status: string;
	    error?: string;
	
	    static createFrom(source: any = {}) {
	        return new MoveLog(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.source = source["source"];
	        this.destination = source["destination"];
	        this.status = source["status"];
	        this.error = source["error"];
	    }
	}
	
	export class OperationLog {
	    id: string;
	    // Go type: time
	    timestamp: any;
	    type: string;
	    items: MoveLog[];
	    total_items: number;
	    success_count: number;
	    failed_count: number;
	    skipped_count: number;
	    status: string;
	
	    static createFrom(source: any = {}) {
	        return new OperationLog(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.id = source["id"];
	        this.timestamp = this.convertValues(source["timestamp"], null);
	        this.type = source["type"];
	        this.items = this.convertValues(source["items"], MoveLog);
	        this.total_items = source["total_items"];
	        this.success_count = source["success_count"];
	        this.failed_count = source["failed_count"];
	        this.skipped_count = source["skipped_count"];
	        this.status = source["status"];
	    }
	
		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}

}

export namespace services {
	
	export class Preferences {
	    json_data_dir: string;
	    default_input_dir: string;
	    batch_size: number;
	    thread_count: number;
	    batch_delay: number;
	    request_timeout: number;
	    avwiki_concurrent_enabled: boolean;
	    avwiki_max_concurrent: number;
	    mode: string;
	    auto_apply_preferences: boolean;
	    cache_ttl_days: number;
	    cache_max_size_mb: number;
	    cache_auto_cleanup_on_exit: boolean;
	    go_enabled: boolean;
	    go_exe_path: string;
	    scan_workers: number;
	    move_conflict_strategy: string;
	    enable_operation_log: boolean;
	    log_dir: string;
	
	    static createFrom(source: any = {}) {
	        return new Preferences(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.json_data_dir = source["json_data_dir"];
	        this.default_input_dir = source["default_input_dir"];
	        this.batch_size = source["batch_size"];
	        this.thread_count = source["thread_count"];
	        this.batch_delay = source["batch_delay"];
	        this.request_timeout = source["request_timeout"];
	        this.avwiki_concurrent_enabled = source["avwiki_concurrent_enabled"];
	        this.avwiki_max_concurrent = source["avwiki_max_concurrent"];
	        this.mode = source["mode"];
	        this.auto_apply_preferences = source["auto_apply_preferences"];
	        this.cache_ttl_days = source["cache_ttl_days"];
	        this.cache_max_size_mb = source["cache_max_size_mb"];
	        this.cache_auto_cleanup_on_exit = source["cache_auto_cleanup_on_exit"];
	        this.go_enabled = source["go_enabled"];
	        this.go_exe_path = source["go_exe_path"];
	        this.scan_workers = source["scan_workers"];
	        this.move_conflict_strategy = source["move_conflict_strategy"];
	        this.enable_operation_log = source["enable_operation_log"];
	        this.log_dir = source["log_dir"];
	    }
	}

}

