CREATE TABLE `knowledge_items` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`node_id` integer NOT NULL,
	`domain` text NOT NULL,
	`content` text NOT NULL,
	`embedding` blob NOT NULL,
	`source_type` text,
	`source_path` text,
	`confidence` real DEFAULT 1,
	`access_count` integer DEFAULT 0,
	`created_at` integer
);
--> statement-breakpoint
CREATE TABLE `knowledge_nodes` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`parent_id` integer,
	`domain` text NOT NULL,
	`depth` integer NOT NULL,
	`embedding` blob NOT NULL,
	`item_count` integer DEFAULT 0,
	`label` text,
	`created_at` integer,
	`updated_at` integer
);
