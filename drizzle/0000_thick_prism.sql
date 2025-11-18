CREATE TABLE `settings` (
	`id` integer PRIMARY KEY DEFAULT 0 NOT NULL,
	`preferred_name` text NOT NULL,
	`api_key` text,
	`api_key_type` text,
	`created_at` integer,
	`updated_at` integer
);
--> statement-breakpoint
CREATE TABLE `folders` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`path` text NOT NULL,
	`name` text NOT NULL,
	`is_favorite` integer DEFAULT false,
	`created_at` integer,
	`updated_at` integer,
	`last_accessed_at` integer
);
--> statement-breakpoint
CREATE UNIQUE INDEX `folders_path_unique` ON `folders` (`path`);