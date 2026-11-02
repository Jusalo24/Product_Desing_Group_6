import { Link, Route, Routes } from "react-router-dom";
import RecipeListPage from "./pages/RecipeListPage";
import RecipeDetailPage from "./pages/RecipeDetailPage";
import RecipeFormPage from "./pages/RecipeFormPage";
import MealSearchPage from "./pages/MealSearchPage";

export default function App() {
  return (
    <>
      <header className="header">
        <Link to="/" className="logo">
          🍲 Recipe App
        </Link>
        <nav aria-label="Main navigation">
          <Link to="/my-recipes" className="button secondary">
            My recipes
          </Link>
        </nav>
        <Link to="/new" className="button">
          + New recipe
        </Link>
      </header>
      <main className="container">
        <Routes>
          <Route path="/" element={<MealSearchPage />} />
          <Route path="/meals/search" element={<MealSearchPage />} />
          <Route path="/my-recipes" element={<RecipeListPage />} />
          <Route path="/my-recipes/new" element={<RecipeFormPage />} />
          <Route path="/new" element={<RecipeFormPage />} />
          <Route path="/recipes/:id" element={<RecipeDetailPage />} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
    </>
  );
}
