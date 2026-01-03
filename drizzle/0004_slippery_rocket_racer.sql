CREATE TABLE `knowledge_metadata` (
	`domain` text PRIMARY KEY NOT NULL,
	`version` integer DEFAULT 1 NOT NULL,
	`item_hash` text,
	`last_built` integer,
	`node_count` integer,
	`item_count` integer
);
