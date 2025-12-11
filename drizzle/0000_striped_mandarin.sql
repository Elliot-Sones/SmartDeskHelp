CREATE TABLE `settings` (
	`id` integer PRIMARY KEY DEFAULT 0 NOT NULL,
	`preferred_name` text NOT NULL,
	`api_key` text,
	`api_key_type` text,
	`selected_model` text DEFAULT 'anthropic/claude-haiku-4.5' NOT NULL,
	`created_at` integer,
	`updated_at` integer
);
--> statement-breakpoint
CREATE TABLE `chat` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`title` text NOT NULL,
	`status` text DEFAULT 'idle' NOT NULL,
	`created_at` integer,
	`updated_at` integer
);
--> statement-breakpoint
CREATE TABLE `message` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`chat_id` integer NOT NULL,
	`role` text NOT NULL,
	`content` text NOT NULL,
	`created_at` integer,
	FOREIGN KEY (`chat_id`) REFERENCES `chat`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `semantic_files` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`folder_id` integer NOT NULL,
	`path` text NOT NULL,
	`name` text NOT NULL,
	`embedding` blob,
	`content_signature` text,
	`content_embedding` blob,
	`extension` text,
	`indexed_at` integer
);
--> statement-breakpoint
CREATE UNIQUE INDEX `semantic_files_path_unique` ON `semantic_files` (`path`);--> statement-breakpoint
CREATE TABLE `semantic_folders` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`path` text NOT NULL,
	`parent_id` integer,
	`name` text NOT NULL,
	`depth` integer NOT NULL,
	`summary` text,
	`embedding` blob,
	`file_count` integer DEFAULT 0,
	`indexed_at` integer
);
--> statement-breakpoint
CREATE UNIQUE INDEX `semantic_folders_path_unique` ON `semantic_folders` (`path`);