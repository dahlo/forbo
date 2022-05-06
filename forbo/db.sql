CREATE TABLE invoices (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	period TEXT,
	date TEXT,
	amount FLOAT NOT NULL,
	description TEXT,
	category TEXT,
	notes TEXT,
	file_path TEXT
);



CREATE TABLE periods (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	period TEXT NOT NULL UNIQUE,
	start_balance FLOAT,
	end_balance FLOAT,
	notes TEXT
);

