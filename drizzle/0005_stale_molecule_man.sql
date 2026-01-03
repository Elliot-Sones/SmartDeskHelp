CREATE TABLE `semantic_chunks` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`file_id` integer NOT NULL,
	`chunk_index` integer NOT NULL,
	`content` text NOT NULL,
	`embedding` blob NOT NULL,
	`char_offset` integer NOT NULL
);
--> statement-breakpoint
ALTER TABLE `semantic_files` ADD `chunk_count` integer DEFAULT 0;