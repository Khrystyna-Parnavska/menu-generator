DROP TABLE IF EXISTS `Journal`;
DROP TABLE IF EXISTS `Ingredients_categories_map`;
DROP TABLE IF EXISTS `Shopping_list_ingredients`;
DROP TABLE IF EXISTS `Shopping_list`;
DROP TABLE IF EXISTS `User_favorite_recipes`;
DROP TABLE IF EXISTS `Ingredient_restrictions`;
DROP TABLE IF EXISTS `Recipes_ingredients`;
DROP TABLE IF EXISTS `Menu_meals`; 
DROP TABLE IF EXISTS `User_restrictions`;
DROP TABLE IF EXISTS `Recipes`;
DROP TABLE IF EXISTS `Recipe_categories`;
DROP TABLE IF EXISTS `Ingredients`;
DROP TABLE IF EXISTS `Ingredient_categories`;
DROP TABLE IF EXISTS `Menus`; 
DROP TABLE IF EXISTS `Users`;
DROP TABLE IF EXISTS `Restrictions`;
DROP TABLE IF EXISTS `User_roles`;
DROP TABLE IF EXISTS `Meals`;
DROP TABLE IF EXISTS `Countries`;
DROP TABLE IF EXISTS `Units`;
DROP TABLE IF EXISTS `Data_sources`;



CREATE TABLE `Ingredients`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(150) NOT NULL,
    `external_id` BIGINT UNSIGNED NULL,
    `source_id` SMALLINT UNSIGNED NULL,
    `description` TEXT NULL,
    `density` DECIMAL(6, 4) NOT NULL DEFAULT 1.0000 COMMENT 'grams per ml, used for converting volume measures to weight',
    `thumb` TEXT NULL,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `created_by_user_id` BIGINT UNSIGNED NULL,
    `if_recipe` BOOLEAN NOT NULL DEFAULT 0
);
CREATE TABLE `Recipes_ingredients`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `recipe_id` BIGINT UNSIGNED NOT NULL,
    `ingredient_id` BIGINT UNSIGNED NOT NULL,
    `measure` DECIMAL(6, 2) NOT NULL,
    `unit_id` SMALLINT UNSIGNED NOT NULL,
    `prep_notes` TEXT NULL,
    `order_index` SMALLINT UNSIGNED NOT NULL,
    `source_id` SMALLINT UNSIGNED NULL
);
CREATE TABLE `Users`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `user_name` VARCHAR(255) NOT NULL,
    `email` TEXT NOT NULL,
    `role_id` SMALLINT UNSIGNED NOT NULL,
    `password_hash` TEXT NOT NULL,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `is_active` BOOLEAN NOT NULL DEFAULT 1,
    `country_id` SMALLINT UNSIGNED NULL,
    `timezone` VARCHAR(50) NULL,
    `age_full_years` SMALLINT NULL,
    `birth_date` DATE NULL,
    `gender` VARCHAR(10) NULL,
    `journaling` BOOLEAN NOT NULL DEFAULT 0,
    `is_verified` BOOLEAN DEFAULT FALSE,
    `email_verification_code` VARCHAR(6) NULL
);
CREATE TABLE `Restrictions`(
    `id` SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `name` TEXT NOT NULL,
    `type` VARCHAR(20) NOT NULL COMMENT '\'allergy\', \'diet\', \'intolerance\', \'ban\'',
    `description` TEXT NOT NULL
);
CREATE TABLE `User_restrictions`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `user_id` BIGINT UNSIGNED NOT NULL,
    `restriction_id` SMALLINT UNSIGNED NOT NULL
);
CREATE TABLE `Ingredient_restrictions`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `restriction_id` SMALLINT UNSIGNED NOT NULL,
    `ingredient_id` BIGINT UNSIGNED NOT NULL
);
CREATE TABLE `User_roles`(
    `id` SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(50) NOT NULL,
    `description` TEXT NOT NULL
);
CREATE TABLE `User_favorite_recipes`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `user_id` BIGINT UNSIGNED NOT NULL,
    `recipe_id` BIGINT UNSIGNED NOT NULL,
    `added_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE `Menus`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `user_id` BIGINT UNSIGNED NOT NULL,
    `menu_date` DATE NOT NULL,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `submitted_at` TIMESTAMP NULL
);
CREATE TABLE `Meals`(
    `id` SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(50) NOT NULL COMMENT 'Breakfast, Lunch, Dinner, Snack_morning, Snack_afternoon, Snack_evening',
    `default_time` TIME NOT NULL
);
CREATE TABLE `Recipe_categories`(
    `id` SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `name` TEXT NOT NULL,
    `thumb` TEXT NULL,
    `description` TEXT NULL,
    `source_id` SMALLINT UNSIGNED NULL
);
CREATE TABLE `Countries`(
    `id` SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(100) NOT NULL,
    `code` CHAR(2) NOT NULL
);
CREATE TABLE `Menu_meals`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `menu_id` BIGINT UNSIGNED NOT NULL,
    `meal_id` SMALLINT UNSIGNED NOT NULL,
    `recipe_id` BIGINT UNSIGNED NOT NULL,
    `meal_time` TIME NOT NULL,
    `regenerated_times` BIGINT UNSIGNED NOT NULL,
    `if_picked_manually` BOOLEAN NOT NULL DEFAULT 0,
    `reminder_sent` BOOLEAN NOT NULL DEFAULT 0
);
CREATE TABLE `Recipes`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `name` TEXT NOT NULL,
    `source_id` SMALLINT UNSIGNED NULL,
    `external_id` BIGINT UNSIGNED NULL,
    `country_id` SMALLINT UNSIGNED NULL,
    `category_id` SMALLINT UNSIGNED NOT NULL,
    `if_breakfast` BOOLEAN NOT NULL DEFAULT 0,
    `if_lunch` BOOLEAN NOT NULL DEFAULT 0,
    `if_dinner` BOOLEAN NOT NULL DEFAULT 0,
    `if_morning_snack` BOOLEAN NOT NULL DEFAULT 0,
    `if_afternoon_snack` BOOLEAN NOT NULL DEFAULT 0,
    `if_evening_snack` BOOLEAN NOT NULL DEFAULT 0,
    `n_portions` SMALLINT NOT NULL DEFAULT 4,
    `prep_time` TIME NOT NULL DEFAULT '00:30:00',
    `cooking_time` TIME NOT NULL DEFAULT '00:30:00',
    `instructions` TEXT NULL,
    `area` TEXT NOT NULL,
    `thumb` TEXT NULL,
    `source_url` TEXT NULL,
    `youtube` TEXT NULL,
    `rating` SMALLINT UNSIGNED NOT NULL DEFAULT 5,
    `created_by_user_id` BIGINT UNSIGNED NULL COMMENT 'if added by user, specifies user id',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE `Shopping_list`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(255) NOT NULL DEFAULT 'My Shopping List',
    `user_id` BIGINT UNSIGNED NULL,
    `menu_id` BIGINT UNSIGNED NULL,
    `is_menu` BOOLEAN NOT NULL DEFAULT 0,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE `Shopping_list_ingredients`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `shop_list_id` BIGINT UNSIGNED NOT NULL,
    `ingredient_id` BIGINT UNSIGNED NULL,
    `item_name` TEXT NULL COMMENT 'used if ingredient is not in the ingredients table',
    `category_id` SMALLINT UNSIGNED NULL,
    `measure` DECIMAL(6,2) UNSIGNED NOT NULL,
    `units` TEXT NOT NULL,
    `if_checked` BOOLEAN DEFAULT FALSE
);

CREATE TABLE `Ingredient_categories`(
    `id` SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `name` TEXT NOT NULL,
    `description` TEXT NULL,
    `subcategories_wweia` TEXT NULL,
    `source_id` SMALLINT UNSIGNED NULL
);

CREATE TABLE `Data_sources`(
    `id` SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(255) NOT NULL,
    `description` TEXT NULL
);

CREATE TABLE `Units`(
    `id` SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(50) NOT NULL,
    `description` TEXT NULL,
    `category` VARCHAR(50) NOT NULL COMMENT 'volume, weight, count, other',
    `base_unit` VARCHAR(50) NULL COMMENT 'references id of the base unit for this unit (e.g. grams for weight, ml for volume)',
    `factor` DECIMAL(6,2) UNSIGNED NOT NULL,
    `notes` TEXT NULL,
    `source_id` SMALLINT UNSIGNED NULL
);

CREATE TABLE `Ingredients_categories_map`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `ingredient_id` BIGINT UNSIGNED NOT NULL,
    `category_id` SMALLINT UNSIGNED NOT NULL,
    `user_id` BIGINT UNSIGNED NULL,
    `source_id` SMALLINT UNSIGNED NULL
);

CREATE TABLE Journal (
`id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
`user_id` BIGINT UNSIGNED NOT NULL, 
`menu_meal_id` BIGINT UNSIGNED NULL,
`meal_as_planned` BOOLEAN NOT NULL DEFAULT 1,
`meal_id` SMALLINT UNSIGNED NULL COMMENT "if meal_as_planned 0",
`meal_fact` TEXT NULL COMMENT "if meal_as_planned 0",
`recipe_id` BIGINT UNSIGNED NULL COMMENT "if meal_as_planned 0",
`time_fact` TIME NOT NULL COMMENT "if meal_as_planned 0",
`mood` SMALLINT NOT NULL COMMENT "1 - 10",
`thoughts` TEXT NULL,
`created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
`submitted_at` TIMESTAMP NULL,
`notified` BOOLEAN NOT NULL DEFAULT 0
);
ALTER TABLE
    `Ingredient_restrictions` ADD CONSTRAINT `ingredient_restrictions_restriction_id_foreign` FOREIGN KEY(`restriction_id`) REFERENCES `Restrictions`(`id`);
ALTER TABLE
    `User_favorite_recipes` ADD CONSTRAINT `user_favorite_recipes_recipe_id_foreign` FOREIGN KEY(`recipe_id`) REFERENCES `Recipes`(`id`);
ALTER TABLE
    `User_restrictions` ADD CONSTRAINT `user_restrictions_restriction_id_foreign` FOREIGN KEY(`restriction_id`) REFERENCES `Restrictions`(`id`);
ALTER TABLE
    `Recipes_ingredients` ADD CONSTRAINT `recipes_ingredients_recipe_id_foreign` FOREIGN KEY(`recipe_id`) REFERENCES `Recipes`(`id`);
ALTER TABLE
    `Menu_meals` ADD CONSTRAINT `menu_meals_recipe_id_foreign` FOREIGN KEY(`recipe_id`) REFERENCES `Recipes`(`id`);
ALTER TABLE
    `Recipes` ADD CONSTRAINT `recipes_country_id_foreign` FOREIGN KEY(`country_id`) REFERENCES `Countries`(`id`);
ALTER TABLE
    `User_favorite_recipes` ADD CONSTRAINT `user_favorite_recipes_user_id_foreign` FOREIGN KEY(`user_id`) REFERENCES `Users`(`id`);
ALTER TABLE
    `Recipes_ingredients` ADD CONSTRAINT `recipes_ingredients_ingredient_id_foreign` FOREIGN KEY(`ingredient_id`) REFERENCES `Ingredients`(`id`);
ALTER TABLE 
    `Shopping_list` ADD CONSTRAINT `shopping_list_menu_id_foreign` FOREIGN KEY (`menu_id`) REFERENCES `Menus`(`id`) ON DELETE SET NULL;
ALTER TABLE
    `Users` ADD CONSTRAINT `users_role_id_foreign` FOREIGN KEY(`role_id`) REFERENCES `User_roles`(`id`);
ALTER TABLE
    `Ingredient_restrictions` ADD CONSTRAINT `ingredient_restrictions_ingredient_id_foreign` FOREIGN KEY(`ingredient_id`) REFERENCES `Ingredients`(`id`);
ALTER TABLE
    `Menu_meals` ADD CONSTRAINT `menu_meals_menu_id_foreign` FOREIGN KEY(`menu_id`) REFERENCES `Menus`(`id`);
ALTER TABLE
    `Menu_meals` ADD CONSTRAINT `menu_meals_meal_id_foreign` FOREIGN KEY(`meal_id`) REFERENCES `Meals`(`id`);
ALTER TABLE
    `User_restrictions` ADD CONSTRAINT `user_restrictions_user_id_foreign` FOREIGN KEY(`user_id`) REFERENCES `Users`(`id`);
ALTER TABLE
    `Menus` ADD CONSTRAINT `menus_user_id_foreign` FOREIGN KEY(`user_id`) REFERENCES `Users`(`id`);
ALTER TABLE
    `Recipes` ADD CONSTRAINT `recipes_created_by_user_id_foreign` FOREIGN KEY(`created_by_user_id`) REFERENCES `Users`(`id`);
ALTER TABLE
    `Ingredients` ADD CONSTRAINT `ingredients_created_by_user_id_foreign` FOREIGN KEY(`created_by_user_id`) REFERENCES `Users`(`id`);
ALTER TABLE
    `Shopping_list_ingredients` ADD CONSTRAINT `shopping_list_ingredients_shop_list_id_foreign` FOREIGN KEY(`shop_list_id`) REFERENCES `Shopping_list`(`id`);
ALTER TABLE
    `Ingredients` ADD CONSTRAINT `ingredients_source_id_foreign` FOREIGN KEY(`source_id`) REFERENCES `Data_sources`(`id`);
ALTER TABLE
    `Recipes` ADD CONSTRAINT `recipes_source_id_foreign` FOREIGN KEY(`source_id`) REFERENCES `Data_sources`(`id`);
ALTER TABLE
    `Recipe_categories` ADD CONSTRAINT `recipe_categories_source_id_foreign` FOREIGN KEY(`source_id`) REFERENCES `Data_sources`(`id`);
ALTER TABLE
    `Recipes_ingredients` ADD CONSTRAINT `recipes_ingredients_unit_id_foreign` FOREIGN KEY(`unit_id`) REFERENCES `Units`(`id`);
ALTER TABLE
    `Ingredients_categories_map` ADD CONSTRAINT `ingredients_categories_map_category_id_foreign` FOREIGN KEY(`category_id`) REFERENCES `Ingredient_categories`(`id`);
ALTER TABLE
    `Ingredients_categories_map` ADD CONSTRAINT `ingredients_categories_map_ingredient_id_foreign` FOREIGN KEY(`ingredient_id`) REFERENCES `Ingredients`(`id`); 
ALTER TABLE
    `Ingredients_categories_map` ADD CONSTRAINT `ingredients_categories_map_user_id_foreign` FOREIGN KEY(`user_id`) REFERENCES `Users`(`id`);
ALTER TABLE
    `Ingredients_categories_map` ADD CONSTRAINT `ingredients_categories_map_source_id_foreign` FOREIGN KEY(`source_id`) REFERENCES `Data_sources`(`id`);
ALTER TABLE
    `Ingredient_categories` ADD CONSTRAINT `ingredient_categories_source_id_foreign` FOREIGN KEY(`source_id`) REFERENCES `Data_sources`(`id`);
ALTER TABLE
    `Units` ADD CONSTRAINT `units_source_id_foreign` FOREIGN KEY(`source_id`) REFERENCES `Data_sources`(`id`);
ALTER TABLE
    `Shopping_list_ingredients` ADD CONSTRAINT `shopping_list_ingredients_category_id_foreign` FOREIGN KEY(`category_id`) REFERENCES `Ingredient_categories`(`id`);
ALTER TABLE
    `Shopping_list_ingredients` ADD CONSTRAINT `shopping_list_ingredients_ingredient_id_foreign` FOREIGN KEY(`ingredient_id`) REFERENCES `Ingredients`(`id`);
ALTER TABLE
    `Journal` ADD CONSTRAINT `journal_user_id_foreign` FOREIGN KEY(`user_id`) REFERENCES `Users`(`id`);
ALTER TABLE
    `Journal` ADD CONSTRAINT `journal_menu_meal_id_foreign` FOREIGN KEY(`menu_meal_id`) REFERENCES `Menu_meals`(`id`);
ALTER TABLE
    `Journal` ADD CONSTRAINT `journal_meal_id_foreign` FOREIGN KEY(`meal_id`) REFERENCES `Meals`(`id`);
ALTER TABLE
    `Journal` ADD CONSTRAINT `journal_recipe_id_foreign` FOREIGN KEY(`recipe_id`) REFERENCES `Recipes`(`id`);