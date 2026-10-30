import { Link, Route, Routes } from "react-router-dom";
import RecipeListPage from "./pages/RecipeListPage";
import RecipeDetailPage from "./pages/RecipeDetailPage";
import RecipeFormPage from "./pages/RecipeFormPage";

export default function App() {
  return (
    <>
      <header className="header">
        <Link to="/" className="logo">
          🍲 Recipe App
        </Link>
        <Link to="/new" className="button">
          + New recipe
        </Link>
      </header>
      <main className="container">
        <Routes>
          <Route path="/" element={<RecipeListPage />} />
          <Route path="/new" element={<RecipeFormPage />} />
          <Route path="/recipes/:id" element={<RecipeDetailPage />} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
    </>
  );
}
