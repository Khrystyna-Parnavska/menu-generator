import os
from database.models import BaseModel

recipe_categories_model = BaseModel('Recipe_categories')
data_sources_model = BaseModel('Data_sources')
country_model = BaseModel('Countries')

menu_generator_id = data_sources_model.run_query("SELECT id FROM Data_sources WHERE name = %s", ('Menu_Generator',))[0]['id']

recipe_categories_model.populate_from_csv(os.path.join('data', 'recipe_categories_menu_generator.csv'), 'Recipe_categories', delimiter=',')
recipe_categories_model.run_query("UPDATE Recipe_categories SET source_id = %s WHERE source_id IS NULL", (menu_generator_id,))

country_model.insert({'name': 'None', 'code': '00'})