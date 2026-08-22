-- =====================================================================
-- 02_fix_shopping_list.sql
-- Run this AFTER run_migration.py has loaded the CSVs.
-- Repoints Shopping_list_ingredients.category_id at the new category IDs.
-- =====================================================================

-- Case A: rows linked to a real ingredient -> use the accurate new map
UPDATE `Shopping_list_ingredients` sli
JOIN `Ingredients_categories_map` icm ON icm.ingredient_id = sli.ingredient_id
SET sli.category_id = icm.category_id
WHERE sli.ingredient_id IS NOT NULL;

-- Case B: manual/custom items (no ingredient_id) -> best-effort old->new mapping.
-- NOTE: this is a lossy guess for ambiguous old categories (e.g. old "Produce"
-- could have been fruit OR veg). Consider flagging these rows in the app for
-- the user to recheck rather than trusting them silently.
UPDATE `Shopping_list_ingredients`
SET category_id = CASE category_id
  WHEN 1  THEN 1001  -- Prepared Meals
  WHEN 2  THEN 102    -- Produce -> Vegetables (best-guess default)
  WHEN 3  THEN 301    -- Dairy & Eggs -> Milk (best-guess default)
  WHEN 4  THEN 401    -- Meat & Poultry -> Beef/Pork/Lamb
  WHEN 5  THEN 201    -- Bakery -> Bread
  WHEN 6  THEN 601    -- Frozen -> Frozen Veg & Fruit
  WHEN 7  THEN 701    -- Pantry -> Pasta/Rice/Grains
  WHEN 8  THEN 801    -- Snack -> Chips & Crisps
  WHEN 9  THEN 905    -- Alcohol -> Wine & Cider
  WHEN 10 THEN 1301   -- Household -> Cleaning Supplies
  WHEN 11 THEN 1101   -- Baby Food
  WHEN 12 THEN 404    -- Deli & Cured Meats
  WHEN 13 THEN 501    -- Fish & Seafood -> Fresh Fish
  WHEN 14 THEN 902    -- Non-Alcohol -> Juice & Soft Drinks
  WHEN 15 THEN 802    -- Candy -> Confectionery & Sweets
  WHEN 16 THEN 804    -- Sport -> Sports Nutrition
  ELSE 1401           -- Other / Vegan/Vegetarian/GF/DF/Halal/Kosher -> Other
END
WHERE ingredient_id IS NULL;

-- ---------------------------------------------------------------------
-- Sanity checks -- run these manually and eyeball the results before
-- trusting the app against this data.
-- ---------------------------------------------------------------------

-- Any Shopping_list_ingredients row pointing at a category that no longer exists?
SELECT sli.* FROM Shopping_list_ingredients sli
LEFT JOIN Ingredient_categories ic ON ic.id = sli.category_id
WHERE sli.category_id IS NOT NULL AND ic.id IS NULL;

-- How many custom (no-ingredient) items landed in each new category?
SELECT ic.name, COUNT(*) AS n
FROM Shopping_list_ingredients sli
JOIN Ingredient_categories ic ON ic.id = sli.category_id
WHERE sli.ingredient_id IS NULL
GROUP BY ic.name
ORDER BY n DESC;

-- Confirm every ingredient got exactly one category
SELECT ingredient_id, COUNT(*) FROM Ingredients_categories_map
GROUP BY ingredient_id HAVING COUNT(*) > 1;
