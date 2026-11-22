/- Synthetic fixture for tests and examples; not a proof corpus. -/
namespace Demo

theorem true_one : True := by
  exact True.intro

theorem true_two : True := by
  exact true_one

def labelA : String := "alpha"
def labelB : String := "beta"

end Demo
