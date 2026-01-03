DROP TABLE IF EXISTS `User_favorit_recipes`;
DROP TABLE IF EXISTS `Ingredient_restrictions`;
DROP TABLE IF EXISTS `Recipes_ingredients`;
DROP TABLE IF EXISTS `Menu_meals`; 
DROP TABLE IF EXISTS `User_restrictions`;
DROP TABLE IF EXISTS `Recipes`;
DROP TABLE IF EXISTS `Ingredients`;
DROP TABLE IF EXISTS `Users`;
DROP TABLE IF EXISTS `Restrictions`;
DROP TABLE IF EXISTS `User_roles`;
DROP TABLE IF EXISTS `Created_menu`;
DROP TABLE IF EXISTS `Meals`;
DROP TABLE IF EXISTS `Countries`;
DROP TABLE IF EXISTS `Categories`;



CREATE TABLE `Recipes`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `name` TEXT NOT NULL,
    `external_id` BIGINT UNSIGNED NULL,
    `country_id` SMALLINT UNSIGNED NULL,
    `meal_id` SMALLINT UNSIGNED NOT NULL,
    `category_id` SMALLINT UNSIGNED NOT NULL,
    `n_portions` SMALLINT UNSIGNED NOT NULL,
    `prep_time` TIME NOT NULL,
    `cooking_time` TIME NOT NULL ,
    `area` TEXT NULL,
    `thumb` TEXT NULL,
    `source_url` TEXT NULL,
    `youtube` TEXT NULL,
    `rating` SMALLINT UNSIGNED NOT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE `Ingredients`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(150) NOT NULL
);
CREATE TABLE `Recipes_ingredients`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `recipe_id` BIGINT UNSIGNED NOT NULL,
    `ingredient_id` BIGINT UNSIGNED NOT NULL,
    `measure` BIGINT UNSIGNED NOT NULL,
    `units` TEXT NOT NULL,
    `order_index` SMALLINT UNSIGNED NOT NULL
);
CREATE TABLE `Users`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `user_name` VARCHAR(255) NOT NULL,
    `email` TEXT NOT NULL,
    `role_id` SMALLINT UNSIGNED NOT NULL,
    `password_hash` BIGINT UNSIGNED NOT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `is_active` BOOLEAN NOT NULL,
    `country_id` SMALLINT UNSIGNED NOT NULL,
    `age_full_years` SMALLINT UNSIGNED NOT NULL,
    `birth_date` DATE NOT NULL,
    `gender` VARCHAR(10) NOT NULL
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
    `Name` VARCHAR(50) NOT NULL
);
CREATE TABLE `User_favorit_recipes`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `user_id` BIGINT UNSIGNED NOT NULL,
    `recipe_id` BIGINT UNSIGNED NOT NULL
);
CREATE TABLE `Created_menu`(
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `user_id` BIGINT UNSIGNED NOT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `submitted_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE `Meals`(
    `id` SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(50) NOT NULL COMMENT 'Breakfast, Lunch, Dinner, Snack_morning, Snack_afternoon, Snack_evening',
    `default_time` TIME NOT NULL
);
CREATE TABLE `Categories`(
    `id` SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `name` TEXT NOT NULL
);
CREATE TABLE `Countries`(
    `id` SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `name` TEXT NOT NULL
);
CREATE TABLE `Menu_meals`(
    `id` SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `menu_id` BIGINT UNSIGNED NOT NULL,
    `meal_id` SMALLINT UNSIGNED NOT NULL,
    `recipe_id` BIGINT UNSIGNED NOT NULL,
    `meal_time` TIME NOT NULL,
    `regenerated_times` BIGINT UNSIGNED NOT NULL,
    `if_picked_manually` BOOLEAN NOT NULL,
    `submitted_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE
    `Ingredient_restrictions` ADD CONSTRAINT `ingredient_restrictions_restriction_id_foreign` FOREIGN KEY(`restriction_id`) REFERENCES `Restrictions`(`id`);
ALTER TABLE
    `User_favorit_recipes` ADD CONSTRAINT `user_favorit_recipes_recipe_id_foreign` FOREIGN KEY(`recipe_id`) REFERENCES `Recipes`(`id`);
ALTER TABLE
    `User_restrictions` ADD CONSTRAINT `user_restrictions_restriction_id_foreign` FOREIGN KEY(`restriction_id`) REFERENCES `Restrictions`(`id`);
ALTER TABLE
    `Recipes_ingredients` ADD CONSTRAINT `recipes_ingredients_recipe_id_foreign` FOREIGN KEY(`recipe_id`) REFERENCES `Recipes`(`id`);
ALTER TABLE
    `Recipes` ADD CONSTRAINT `recipes_meal_id_foreign` FOREIGN KEY(`meal_id`) REFERENCES `Meals`(`id`);
ALTER TABLE
    `Menu_meals` ADD CONSTRAINT `menu_meals_recipe_id_foreign` FOREIGN KEY(`recipe_id`) REFERENCES `Recipes`(`id`);
ALTER TABLE
    `Recipes` ADD CONSTRAINT `recipes_country_id_foreign` FOREIGN KEY(`country_id`) REFERENCES `Countries`(`id`);
ALTER TABLE
    `User_favorit_recipes` ADD CONSTRAINT `user_favorit_recipes_user_id_foreign` FOREIGN KEY(`user_id`) REFERENCES `Users`(`id`);
ALTER TABLE
    `Recipes_ingredients` ADD CONSTRAINT `recipes_ingredients_ingredient_id_foreign` FOREIGN KEY(`ingredient_id`) REFERENCES `Ingredients`(`id`);
ALTER TABLE
    `Users` ADD CONSTRAINT `users_role_id_foreign` FOREIGN KEY(`role_id`) REFERENCES `User_roles`(`id`);
ALTER TABLE
    `Recipes` ADD CONSTRAINT `recipes_category_id_foreign` FOREIGN KEY(`category_id`) REFERENCES `Categories`(`id`);
ALTER TABLE
    `Ingredient_restrictions` ADD CONSTRAINT `ingredient_restrictions_ingredient_id_foreign` FOREIGN KEY(`ingredient_id`) REFERENCES `Ingredients`(`id`);
ALTER TABLE
    `Menu_meals` ADD CONSTRAINT `menu_meals_menu_id_foreign` FOREIGN KEY(`menu_id`) REFERENCES `Created_menu`(`id`);
ALTER TABLE
    `Menu_meals` ADD CONSTRAINT `menu_meals_meal_id_foreign` FOREIGN KEY(`meal_id`) REFERENCES `Meals`(`id`);
ALTER TABLE
    `User_restrictions` ADD CONSTRAINT `user_restrictions_user_id_foreign` FOREIGN KEY(`user_id`) REFERENCES `Users`(`id`);