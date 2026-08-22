-- =====================================================================
-- 01_schema.sql
-- Structural changes only -- no data. Run this first, then run
-- run_migration.py to load the CSVs, then 02_fix_shopping_list.sql.
-- =====================================================================

SET FOREIGN_KEY_CHECKS = 0;

-- ---------------------------------------------------------------------
-- New zone table (Fruit & Vegetables, Bakery, Dairy & Eggs, ...)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `Category_groups` (
    `id` SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(100) NOT NULL,
    `description` TEXT NULL
);

-- ---------------------------------------------------------------------
-- Rebuild Ingredient_categories: wipe the old flat list, link it to zones
-- ---------------------------------------------------------------------
TRUNCATE TABLE `Ingredient_categories`;

ALTER TABLE `Ingredient_categories`
  ADD COLUMN `group_id` SMALLINT UNSIGNED NOT NULL;

ALTER TABLE `Ingredient_categories`
  ADD CONSTRAINT `ingredient_categories_group_id_foreign`
  FOREIGN KEY (`group_id`) REFERENCES `Category_groups`(`id`);

-- ---------------------------------------------------------------------
-- Clear the old ingredient->category mapping (new one loaded by the
-- Python script from data/Ingredients_categories_map.csv)
-- ---------------------------------------------------------------------
TRUNCATE TABLE `Ingredients_categories_map`;

SET FOREIGN_KEY_CHECKS = 1;

-- Next step: run `python run_migration.py` to load data/*.csv into
-- category_groups, Ingredient_categories and Ingredients_categories_map.
-- Then run 02_fix_shopping_list.sql.
